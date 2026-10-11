from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from self_learning_agent.models import (
    Conversation,
    Message,
    StoredConversationSummary,
)


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: str) -> Conversation:
        conversation = Conversation(user_id=user_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def list_for_user(self, user_id: str, limit: int = 50) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def add_message(self, conversation_id: UUID, role: str, content: str) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(self, conversation_id: UUID, limit: int | None = None) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        if limit is not None:
            recent_ids = (
                select(Message.id)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
                .subquery()
            )
            statement = (
                select(Message)
                .join(recent_ids, recent_ids.c.id == Message.id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            )
        return list((await self.session.scalars(statement)).all())

    async def store_summary(
        self,
        conversation_id: UUID,
        synopsis: str,
        payload: dict,
    ) -> StoredConversationSummary:
        latest_version = await self.session.scalar(
            select(func.coalesce(func.max(StoredConversationSummary.version), 0)).where(
                StoredConversationSummary.conversation_id == conversation_id
            )
        )
        stored = StoredConversationSummary(
            conversation_id=conversation_id,
            version=int(latest_version or 0) + 1,
            synopsis=synopsis,
            payload=payload,
        )
        self.session.add(stored)
        await self.session.flush()
        return stored

    async def latest_summary(self, conversation_id: UUID) -> StoredConversationSummary | None:
        statement = (
            select(StoredConversationSummary)
            .where(StoredConversationSummary.conversation_id == conversation_id)
            .order_by(StoredConversationSummary.version.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def finalize(self, conversation: Conversation) -> None:
        conversation.status = "finalized"
        conversation.finalized_at = datetime.now(UTC)
        await self.session.flush()
