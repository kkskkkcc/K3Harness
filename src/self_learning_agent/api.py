from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from self_learning_agent.config import Settings, get_settings
from self_learning_agent.db import get_session
from self_learning_agent.domain import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationRead,
    FinalizeResponse,
    MemoryRead,
)
from self_learning_agent.errors import (
    ConfigurationError,
    ConversationFinalizedError,
    ConversationNotFoundError,
    MemoryNotFoundError,
)
from self_learning_agent.llm import OllamaLLMGateway
from self_learning_agent.memory import Mem0MemoryStore
from self_learning_agent.services import AgentService

app = FastAPI(
    title="Self-Learning AI Agent",
    version="0.1.0",
    description=(
        "A memory-augmented assistant that summarizes completed conversations "
        "before creating versioned long-term memories."
    ),
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@lru_cache
def get_local_components() -> tuple[Settings, OllamaLLMGateway, Mem0MemoryStore]:
    settings = get_settings()
    return settings, OllamaLLMGateway(settings), Mem0MemoryStore(settings)


def get_agent_service(session: AsyncSession = Depends(get_session)) -> AgentService:
    try:
        settings, gateway, memory = get_local_components()
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return AgentService(session, gateway, memory, settings)


@app.get("/", include_in_schema=False)
async def chat_interface() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post(
    "/v1/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    service: AgentService = Depends(get_agent_service),
):
    return await service.start_conversation(payload.user_id)


@app.post("/v1/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_message(
    conversation_id: UUID,
    payload: ChatRequest,
    service: AgentService = Depends(get_agent_service),
):
    try:
        return await service.chat(conversation_id, payload.content)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ConversationFinalizedError as exc:
        raise HTTPException(status_code=409, detail="Conversation is finalized") from exc


@app.post(
    "/v1/conversations/{conversation_id}/finalize",
    response_model=FinalizeResponse,
)
async def finalize_conversation(
    conversation_id: UUID,
    service: AgentService = Depends(get_agent_service),
):
    try:
        return await service.finalize(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ConversationFinalizedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/users/{user_id}/memories", response_model=list[MemoryRead])
async def list_memories(
    user_id: str,
    service: AgentService = Depends(get_agent_service),
):
    return await service.list_memories(user_id)


@app.delete(
    "/v1/users/{user_id}/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_memory(
    user_id: str,
    memory_id: str,
    service: AgentService = Depends(get_agent_service),
) -> Response:
    try:
        await service.delete_memory(user_id, memory_id)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
