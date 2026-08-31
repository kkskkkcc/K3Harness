from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from self_learning_agent.config import Settings
from self_learning_agent.domain import (
    ChatResponse,
    ConversationStatus,
    ConversationSummary,
    FinalizeResponse,
    MemoryCandidate,
    MemoryType,
    MessageRole,
    TranscriptMessage,
)
from self_learning_agent.errors import (
    ConversationFinalizedError,
    ConversationNotFoundError,
)
from self_learning_agent.llm import LLMGateway
from self_learning_agent.memory import MemoryStore
from self_learning_agent.models import Conversation, Message
from self_learning_agent.repositories import ConversationRepository


def to_transcript(messages: list[Message]) -> list[TranscriptMessage]:
    return [
        TranscriptMessage(
            id=message.id,
            role=MessageRole(message.role),
            content=message.content,
            created_at=message.created_at,
        )
        for message in messages
    ]


def is_durable_user_statement(content: str) -> bool:
    """Reject greetings and information requests as sources for profile memory."""
    normalized = " ".join(content.lower().split())
    if len(normalized) < 8 or normalized in {"hello", "hi there", "hey there"}:
        return False
    request_prefixes = (
        "can ",
        "could ",
        "would ",
        "please ",
        "give ",
        "tell ",
        "list ",
        "what ",
        "who ",
        "when ",
        "where ",
        "why ",
        "how ",
    )
    return not normalized.endswith("?") and not normalized.startswith(request_prefixes)


def explicit_user_memory_candidates(
    messages: list[TranscriptMessage],
) -> list[MemoryCandidate]:
    """Extract a few high-confidence profile facts without another model call."""
    candidates: list[MemoryCandidate] = []
    patterns = (
        (
            re.compile(r"^my name is\s+(.+?)[.!]?$", re.IGNORECASE),
            MemoryType.SEMANTIC,
            lambda match: f"The user's name is {match.group(1).strip()}.",
        ),
        (
            re.compile(r"^my (?:favorite|fav)\s+(.+?)\s+is\s+(.+?)[.!]?$", re.IGNORECASE),
            MemoryType.PREFERENCE,
            lambda match: (
                f"The user's favorite {match.group(1).strip()} is {match.group(2).strip()}."
            ),
        ),
        (
            re.compile(r"^i prefer\s+(.+?)[.!]?$", re.IGNORECASE),
            MemoryType.PREFERENCE,
            lambda match: f"The user prefers {match.group(1).strip()}.",
        ),
    )
    for message in messages:
        if message.role != MessageRole.USER:
            continue
        for pattern, memory_type, render in patterns:
            if match := pattern.match(message.content.strip()):
                candidates.append(
                    MemoryCandidate(
                        content=render(match),
                        memory_type=memory_type,
                        confidence=0.99,
                        source_message_ids=[message.id],
                    )
                )
                break
    return candidates


def validate_summary_sources(
    summary: ConversationSummary,
    messages: list[TranscriptMessage],
) -> ConversationSummary:
    """Remove unsupported source IDs before the summary can reach long-term memory."""
    messages_by_id = {message.id: message for message in messages}
    candidates: list[MemoryCandidate] = []
    for candidate in summary.candidate_memories:
        if candidate.memory_type == MemoryType.EPISODIC:
            continue
        valid_sources = [
            source_id
            for source_id in candidate.source_message_ids
            if source_id in messages_by_id
            and (
                candidate.memory_type == MemoryType.EPISODIC
                or (
                    messages_by_id[source_id].role == MessageRole.USER
                    and is_durable_user_statement(messages_by_id[source_id].content)
                )
            )
        ]
        if valid_sources:
            candidates.append(candidate.model_copy(update={"source_message_ids": valid_sources}))

    known_contents = {candidate.content.casefold() for candidate in candidates}
    for candidate in explicit_user_memory_candidates(messages):
        if candidate.content.casefold() not in known_contents:
            candidates.append(candidate)
            known_contents.add(candidate.content.casefold())

    return summary.model_copy(update={"candidate_memories": candidates})


class AgentService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMGateway,
        memory: MemoryStore,
        settings: Settings,
    ) -> None:
        self.session = session
        self.llm = llm
        self.memory = memory
        self.settings = settings
        self.conversations = ConversationRepository(session)

    async def start_conversation(self, user_id: str) -> Conversation:
        conversation = await self.conversations.create(user_id)
        await self.session.commit()
        return conversation

    async def chat(self, conversation_id: UUID, content: str) -> ChatResponse:
        conversation = await self._active_conversation(conversation_id)
        await self.conversations.add_message(conversation_id, MessageRole.USER.value, content)
        await self.session.commit()

        recalled = await self.memory.search(
            conversation.user_id, content, self.settings.memory_retrieval_limit
        )
        recent_records = await self.conversations.list_messages(
            conversation_id, self.settings.recent_message_limit
        )
        await self.session.commit()

        answer = await self.llm.answer(content, to_transcript(recent_records), recalled)
        assistant_message = await self.conversations.add_message(
            conversation_id, MessageRole.ASSISTANT.value, answer
        )
        await self.session.commit()

        return ChatResponse(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            content=answer,
            recalled_memories=recalled,
        )

    async def finalize(self, conversation_id: UUID) -> FinalizeResponse:
        conversation = await self._active_conversation(conversation_id)
        message_records = await self.conversations.list_messages(conversation_id)
        await self.session.commit()
        messages = to_transcript(message_records)
        if not messages:
            raise ConversationFinalizedError("Cannot finalize an empty conversation.")

        summary = validate_summary_sources(await self.llm.summarize(messages), messages)
        await self.conversations.store_summary(
            conversation_id,
            summary.synopsis,
            summary.model_dump(mode="json"),
        )
        await self.session.commit()

        memory_actions = await self.memory.add_summary(
            conversation.user_id, conversation_id, summary
        )
        await self.conversations.finalize(conversation)
        await self.session.commit()

        return FinalizeResponse(
            conversation_id=conversation_id,
            summary=summary,
            memory_actions=memory_actions,
        )

    async def list_memories(self, user_id: str):
        return await self.memory.list(user_id)

    async def delete_memory(self, user_id: str, memory_id: str) -> None:
        await self.memory.delete(user_id, memory_id)

    async def _active_conversation(self, conversation_id: UUID) -> Conversation:
        conversation = await self.conversations.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError(str(conversation_id))
        if conversation.status != ConversationStatus.ACTIVE.value:
            raise ConversationFinalizedError(str(conversation_id))
        return conversation
