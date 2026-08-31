from __future__ import annotations

import asyncio
import os
from collections import Counter
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from self_learning_agent.config import Settings
from self_learning_agent.domain import (
    ConversationSummary,
    MemoryAction,
    MemoryRead,
    RetrievedMemory,
)
from self_learning_agent.errors import ConfigurationError, MemoryNotFoundError

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
