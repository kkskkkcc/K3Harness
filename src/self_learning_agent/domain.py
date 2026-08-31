from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationStatus(str, Enum):
    ACTIVE = "active"
    FINALIZED = "finalized"


class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"


class MemoryAction(str, Enum):
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
    NO_CHANGE = "no_change"


class TranscriptMessage(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    created_at: datetime


class MemoryCandidate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    memory_type: MemoryType
    confidence: Confidence
    source_message_ids: list[UUID] = Field(min_length=1)


class ConversationSummary(BaseModel):
    synopsis: str = Field(min_length=1, max_length=5000)
    user_goals: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    successful_actions: list[str] = Field(default_factory=list)
    failed_actions: list[str] = Field(default_factory=list)
    candidate_memories: list[MemoryCandidate] = Field(default_factory=list)


class RetrievedMemory(BaseModel):
    id: str
    content: str
    score: float
    metadata: dict = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: str
    status: ConversationStatus
    created_at: datetime


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    content: str
    recalled_memories: list[RetrievedMemory]


class FinalizeResponse(BaseModel):
    conversation_id: UUID
    summary: ConversationSummary
    memory_actions: dict[MemoryAction, int]


class MemoryRead(BaseModel):
    id: str
    user_id: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
