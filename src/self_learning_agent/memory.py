from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import httpx
from sqlalchemy import select

from self_learning_agent.config import Settings
from self_learning_agent.domain import (
    ConversationSummary,
    MemoryAction,
    MemoryRead,
    RetrievedMemory,
)
from self_learning_agent.errors import ConfigurationError, MemoryNotFoundError
from self_learning_agent.models import MemoryRecord

logger = logging.getLogger(__name__)

MEM0_CUSTOM_INSTRUCTIONS = """
Create long-term memories only from the supplied completed-conversation summary.
Keep facts atomic and useful in future conversations. Prefer explicit user facts,
goals, stable preferences, decisions, and successful procedures. Exclude greetings,
filler, secrets, unsupported assistant claims, and short-lived details. Update or
delete an older memory when the summary clearly refines or contradicts it.
Use non-thinking mode for this extraction task. /no_think
""".strip()


class MemoryStore(Protocol):
    async def search(self, user_id: str, query: str, limit: int) -> list[RetrievedMemory]: ...

    async def add_summary(
        self,
        user_id: str,
        conversation_id: UUID,
        summary: ConversationSummary,
    ) -> dict[MemoryAction, int]: ...

    async def list(self, user_id: str) -> list[MemoryRead]: ...

    async def delete(self, user_id: str, memory_id: str) -> None: ...


def _lexical_score(query: str, content: str) -> float:
    query_words = {word for word in query.lower().split() if len(word) > 1}
    content_words = {word for word in content.lower().split() if len(word) > 1}
    if not query_words or not content_words:
        return 0.0
    return len(query_words & content_words) / max(len(query_words), len(content_words))


def _cosine(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def _extract_first_embedding(result: Any) -> list[float] | None:
    """Pull the first embedding vector out of an ollama response.

    ``EmbedResponse`` exposes ``embeddings`` (``Sequence[Sequence[float]]``)
    while the deprecated ``EmbeddingsResponse`` exposes ``embedding``
    (``Sequence[float]``). Both should be normalised to a plain ``list[float]``.
    """
    embeddings = getattr(result, "embeddings", None)
    if embeddings is None and isinstance(result, dict):
        embeddings = result.get("embeddings")
    if embeddings:
        try:
            return list(embeddings[0])
        except (TypeError, IndexError):
            return None
    embedding = getattr(result, "embedding", None)
    if embedding is None and isinstance(result, dict):
        embedding = result.get("embedding")
    if embedding:
        return list(embedding)
    return None


class LocalMemoryStore:
    """SQLite-backed memory with optional Ollama embeddings and lexical fallback."""

    def __init__(self, settings: Settings) -> None:
        from ollama import AsyncClient

        from self_learning_agent.db import SessionFactory

        self._settings = settings
        self._sessions = SessionFactory
        self._client = AsyncClient(host=settings.ollama_base_url, trust_env=False)

    async def _embed(self, text: str) -> list[float] | None:
        """Try the modern ``/api/embed`` endpoint first, then fall back to the
        legacy ``/api/embeddings`` endpoint. Older Ollama builds (or models that
        were registered before the ``embed`` route existed) still respond to
        the legacy endpoint, so trying both makes the memory store usable on a
        broader range of local Ollama installations.
        """
        model = self._settings.ollama_embedding_model
        # Modern path: ollama-python 0.5+ posts to /api/embed with an
        # ``input`` field. A response error here is not fatal because we may
        # still get a hit on the legacy endpoint below.
        try:
            result = await asyncio.wait_for(
                self._client.embed(model=model, input=text),
                timeout=2.0,
            )
            return _extract_first_embedding(result)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                logger.debug("embedding /api/embed failed: %s", exc)
                return None
        except Exception as exc:  # network/timeout/connection failures
            logger.debug("embedding /api/embed failed: %s", exc)
            return None
        # Legacy fallback: ``/api/embeddings`` with ``prompt`` field.
        try:
            result = await asyncio.wait_for(
                self._client.embeddings(model=model, prompt=text),
                timeout=2.0,
            )
            return _extract_first_embedding(result)
        except Exception as exc:
            logger.debug("embedding /api/embeddings failed: %s", exc)
            return None

    async def search(self, user_id: str, query: str, limit: int) -> list[RetrievedMemory]:
        query_embedding = await self._embed(query)
        async with self._sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(MemoryRecord).where(MemoryRecord.user_id == user_id)
                    )
                ).all()
            )
        ranked = sorted(
            rows,
            key=lambda row: max(
                _cosine(query_embedding, row.embedding),
                _lexical_score(query, row.content),
            ),
            reverse=True,
        )
        return [
            RetrievedMemory(
                id=str(row.id),
                content=row.content,
                score=max(
                    _cosine(query_embedding, row.embedding),
                    _lexical_score(query, row.content),
                ),
                metadata=dict(row.metadata_json or {}),
            )
            for row in ranked[:limit]
        ]

    async def add_summary(
        self,
        user_id: str,
        conversation_id: UUID,
        summary: ConversationSummary,
    ) -> dict[MemoryAction, int]:
        counts: Counter[MemoryAction] = Counter()
        async with self._sessions() as session:
            for candidate in summary.candidate_memories:
                existing = list(
                    (
                        await session.scalars(
                            select(MemoryRecord).where(
                                MemoryRecord.user_id == user_id,
                                MemoryRecord.content == candidate.content,
                            )
                        )
                    ).all()
                )
                if existing:
                    row = existing[0]
                    # Refresh both confidence and embedding so a re-summarised
                    # memory continues to surface in semantic recall. The
                    # ``updated_at`` column is touched automatically by the
                    # SQLAlchemy ``onupdate`` hook, so we no longer assign it
                    # here (a self-assignment would also defeat that hook).
                    row.confidence = max(row.confidence, candidate.confidence)
                    row.embedding = await self._embed(candidate.content)
                    counts[MemoryAction.UPDATE] += 1
                    continue
                embedding = await self._embed(candidate.content)
                row = MemoryRecord(
                    user_id=user_id,
                    content=candidate.content,
                    memory_type=candidate.memory_type.value,
                    confidence=candidate.confidence,
                    metadata_json={
                        "source": "validated_conversation_summary",
                        "source_conversation_id": str(conversation_id),
                        "source_message_ids": [str(item) for item in candidate.source_message_ids],
                    },
                    embedding=embedding,
                )
                session.add(row)
                counts[MemoryAction.ADD] += 1
            await session.commit()
        return {action: counts[action] for action in MemoryAction}

    async def list(self, user_id: str) -> list[MemoryRead]:
        async with self._sessions() as session:
            rows = list(
                (
                    await session.scalars(
                        select(MemoryRecord).where(MemoryRecord.user_id == user_id)
                    )
                ).all()
            )
        return [
            MemoryRead(
                id=str(row.id),
                user_id=row.user_id,
                content=row.content,
                metadata=dict(row.metadata_json or {}),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def delete(self, user_id: str, memory_id: str) -> None:
        async with self._sessions() as session:
            row = await session.get(MemoryRecord, memory_id)
            if row is None or row.user_id != user_id:
                raise MemoryNotFoundError(memory_id)
            await session.delete(row)
            await session.commit()


def format_summary_for_memory(summary: ConversationSummary) -> str:
    """Give Mem0 only candidates whose source messages were already validated."""
    return "Validated durable memory candidates:\n" + "\n".join(
        f"- {candidate.content}" for candidate in summary.candidate_memories
    )


def mem0_results(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        results = payload.get("results", [])
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def count_memory_actions(payload: Any) -> dict[MemoryAction, int]:
    counts: Counter[MemoryAction] = Counter()
    mapping = {
        "ADD": MemoryAction.ADD,
        "UPDATE": MemoryAction.UPDATE,
        "DELETE": MemoryAction.DELETE,
        "NONE": MemoryAction.NO_CHANGE,
        "NO_CHANGE": MemoryAction.NO_CHANGE,
    }
    for item in mem0_results(payload):
        action = mapping.get(str(item.get("event", "NONE")).upper())
        if action is not None:
            counts[action] += 1
    return {action: counts[action] for action in MemoryAction}


def build_mem0_config(settings: Settings, history_path: Path) -> dict[str, Any]:
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": settings.mem0_qdrant_collection,
                "host": settings.mem0_qdrant_host,
                "port": settings.mem0_qdrant_port,
                "embedding_model_dims": settings.ollama_embedding_dimensions,
            },
        },
        "llm": {
            "provider": "ollama",
            "config": {
                "model": settings.ollama_summary_model,
                "temperature": 0,
                "max_tokens": settings.ollama_summary_max_tokens,
                "ollama_base_url": settings.ollama_base_url,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": settings.ollama_embedding_model,
                "embedding_dims": settings.ollama_embedding_dimensions,
                "ollama_base_url": settings.ollama_base_url,
            },
        },
        "history_db_path": str(history_path),
        "custom_instructions": MEM0_CUSTOM_INSTRUCTIONS,
        "version": "v1.1",
    }


class Mem0MemoryStore:
    def __init__(self, settings: Settings) -> None:
        history_path = Path(settings.mem0_history_db_path)
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("MEM0_DIR", str(history_path.parent / "mem0_config"))
            os.environ["MEM0_TELEMETRY"] = str(settings.mem0_telemetry)
            from mem0 import Memory

            self._client = Memory.from_config(build_mem0_config(settings, history_path))
        except Exception as exc:
            raise ConfigurationError(f"Unable to initialize local Mem0: {exc}") from exc

    async def search(self, user_id: str, query: str, limit: int) -> list[RetrievedMemory]:
        payload = await asyncio.to_thread(
            self._client.search,
            query=query,
            filters={"user_id": user_id},
            top_k=limit,
        )
        return [
            RetrievedMemory(
                id=str(item.get("id", "")),
                content=str(item.get("memory") or item.get("content") or ""),
                score=float(item.get("score") or 0.0),
                metadata=dict(item.get("metadata") or {}),
            )
            for item in mem0_results(payload)
            if item.get("memory") or item.get("content")
        ]

    async def add_summary(
        self,
        user_id: str,
        conversation_id: UUID,
        summary: ConversationSummary,
    ) -> dict[MemoryAction, int]:
        if not summary.candidate_memories:
            return {action: 0 for action in MemoryAction}
        totals: Counter[MemoryAction] = Counter()
        for candidate in summary.candidate_memories:
            payload = await asyncio.to_thread(
                self._client.add,
                [{"role": "user", "content": candidate.content}],
                user_id=user_id,
                metadata={
                    "source": "validated_conversation_summary",
                    "memory_type": candidate.memory_type.value,
                    "confidence": candidate.confidence,
                    "source_conversation_id": str(conversation_id),
                    "source_message_ids": [str(item) for item in candidate.source_message_ids],
                },
                infer=False,
            )
            totals.update(count_memory_actions(payload))
        return {action: totals[action] for action in MemoryAction}

    async def list(self, user_id: str) -> list[MemoryRead]:
        payload = await asyncio.to_thread(
            self._client.get_all,
            filters={"user_id": user_id},
            top_k=100,
        )
        return [self._to_memory_read(user_id, item) for item in mem0_results(payload)]

    async def delete(self, user_id: str, memory_id: str) -> None:
        memory = await asyncio.to_thread(self._client.get, memory_id)
        if not isinstance(memory, dict) or memory.get("user_id") != user_id:
            raise MemoryNotFoundError(memory_id)
        await asyncio.to_thread(self._client.delete, memory_id)

    @staticmethod
    def _to_memory_read(user_id: str, item: dict[str, Any]) -> MemoryRead:
        return MemoryRead(
            id=str(item.get("id", "")),
            user_id=user_id,
            content=str(item.get("memory") or item.get("content") or ""),
            metadata=dict(item.get("metadata") or {}),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
