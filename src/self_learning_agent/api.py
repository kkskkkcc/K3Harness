from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from uuid import UUID
from uuid import uuid4 as _uuid4

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from ollama import ResponseError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from self_learning_agent.config import Settings, get_settings
from self_learning_agent.db import get_session, init_db
from self_learning_agent.domain import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationListItem,
    ConversationMessageRead,
    ConversationRead,
    FinalizeResponse,
    MemoryRead,
    ToolRunRequest,
)
from self_learning_agent.errors import (
    ConfigurationError,
    ConversationFinalizedError,
    ConversationNotFoundError,
    MemoryNotFoundError,
)
from self_learning_agent.hardware_gateway import SimulatedHardwareKernel
from self_learning_agent.llm import OllamaLLMGateway
from self_learning_agent.memory import LocalMemoryStore, Mem0MemoryStore
from self_learning_agent.model_profiles import canonical_model_id, list_model_profiles
from self_learning_agent.repositories import ConversationRepository
from self_learning_agent.services import AgentService
from self_learning_agent.tools import TOOL_SCHEMAS, execute_tool
from self_learning_agent.workflows import WORKFLOW_DEFINITIONS, run_workflow


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Self-Learning AI Agent",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "A memory-augmented assistant that summarizes completed conversations "
        "before creating versioned long-term memories."
    ),
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Wrap StaticFiles so every response includes ``Cache-Control: no-store``.
# Without this the browser caches the old HTML/JS and the operator keeps
# seeing a stale UI even after we deploy a fix (e.g. the shutdown button).
class _NoCacheStaticFiles(StaticFiles):
    async def __call__(self, scope, receive, send):  # type: ignore[override]
        await super().__call__(scope, receive, _wrap_send(send))


def _wrap_send(send):
    async def wrapped(message):
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.append((b"cache-control", b"no-store, must-revalidate"))
            headers.append((b"pragma", b"no-cache"))
            message["headers"] = headers
        await send(message)
    return wrapped


app.mount("/static", _NoCacheStaticFiles(directory=STATIC_DIR), name="static")


def model_http_error(exc: ResponseError) -> HTTPException:
    if exc.status_code == 404:
        detail = "所选模型尚未导入 Ollama，请运行项目根目录的模型导入.bat。"
    else:
        reason = str(exc.error or "模型服务没有返回错误详情")[:300]
        detail = f"Ollama 模型调用失败（{exc.status_code}）：{reason}。请检查模型导入和可用内存。"
    return HTTPException(status_code=503, detail=detail)


@lru_cache
def get_local_components() -> tuple[Settings, OllamaLLMGateway, LocalMemoryStore | Mem0MemoryStore]:
    settings = get_settings()
    memory = (
        LocalMemoryStore(settings)
        if settings.memory_backend == "local"
        else Mem0MemoryStore(settings)
    )
    return settings, OllamaLLMGateway(settings), memory


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
    # ``no-store`` so the browser never serves a stale index.html after we
    # deploy a UI change (e.g. the new shutdown button).
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/v1/runtime")
async def runtime() -> dict[str, object]:
    settings = get_settings()
    registered: set[str] = set()
    ollama_online = False
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=2) as client:
            response = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            registered = {item["name"] for item in response.json().get("models", [])}
            ollama_online = True
    except (httpx.HTTPError, ValueError, KeyError):
        pass
    embedding_available = await _embedding_available(settings, registered)
    workspace_path, project_root = await asyncio.gather(
        asyncio.to_thread(Path(settings.agent_workspace).resolve),
        asyncio.to_thread(Path(settings.project_root).resolve),
    )
    return {
        "default_model": canonical_model_id(None, settings.ollama_chat_model),
        "default_reasoning_effort": "balanced",
        "models": [
            {**profile, "registered": profile["id"] in registered}
            for profile in list_model_profiles()
        ],
        "ollama_online": ollama_online,
        "latency_target_seconds": settings.latency_target_seconds,
        "filesystem": {
            "mode": settings.file_access_mode,
            "workspace": str(workspace_path),
            "project_root": str(project_root),
            "read_only": True,
        },
        "memory": {
            "backend": settings.memory_backend,
            "embedding_model": settings.ollama_embedding_model,
            "embedding_available": embedding_available,
            "embedding_mode": "semantic" if embedding_available else "lexical",
        },
        "hardware": {
            "enabled": settings.hardware_enabled,
            "mode": settings.hardware_mode,
            "camera_backend": settings.camera_backend,
            "yolo_model_path": settings.yolo_model_path,
        },
    }


async def _embedding_available(settings: Settings, registered: set[str]) -> bool:
    """Return True only when the embedding model can actually serve requests.

    The runtime check is two-step: first confirm the model is registered with
    Ollama (cheap ``/api/tags`` lookup), then probe both ``/api/embed`` and
    the legacy ``/api/embeddings`` endpoint. Older Ollama builds respond only
    to the legacy route, so probing both is necessary to avoid reporting
    "semantic memory" on an installation that actually only has the legacy
    endpoint available.
    """
    if settings.ollama_embedding_model not in registered:
        return False
    base = settings.ollama_base_url.rstrip("/")
    payload_embed = {"model": settings.ollama_embedding_model, "input": "ping"}
    payload_legacy = {"model": settings.ollama_embedding_model, "prompt": "ping"}
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.post(f"{base}/api/embed", json=payload_embed)
            if response.status_code == 200:
                return True
            response = await client.post(f"{base}/api/embeddings", json=payload_legacy)
            return response.status_code == 200
    except (httpx.HTTPError, ValueError, KeyError):
        return False


@app.get("/v1/hardware/status")
async def hardware_status() -> dict[str, object]:
    settings = get_settings()
    gateway = SimulatedHardwareKernel(settings.hardware_enabled, settings.hardware_mode)
    return await gateway.status()


@app.get("/v1/tools")
async def tools_catalog() -> dict[str, object]:
    return {
        "tools": [
            {
                "name": item["function"]["name"],
                "description": item["function"]["description"],
                "parameters": item["function"].get("parameters", {}),
                "safe_for_ui": item["function"]["name"]
                not in {"hardware_command"},
            }
            for item in TOOL_SCHEMAS
        ],
        "workflow_support": {
            "available": True,
            "message": "可运行安全预检工作流；硬件动作仍由网关拒绝。",
        },
    }


@app.post("/v1/tools/execute")
async def run_tool(payload: ToolRunRequest) -> dict[str, object]:
    safe_tools = {
        "workspace_list",
        "workspace_read",
        "calculator",
        "get_time",
        "hardware_status",
        "camera_capture",
    }
    if payload.name not in safe_tools:
        raise HTTPException(status_code=403, detail="该工具只能由 Agent 在受控流程中调用。")
    settings = get_settings()
    try:
        result = await execute_tool(
            payload.name, payload.arguments, settings.agent_workspace,
            project_root=settings.project_root, settings=settings,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": payload.name, "result": result}


@app.get("/v1/workflows")
async def workflows_catalog() -> dict[str, object]:
    return {"workflows": WORKFLOW_DEFINITIONS}


@app.post("/v1/workflows/{workflow_id}/run")
async def run_workflow_endpoint(workflow_id: str) -> dict[str, object]:
    settings = get_settings()
    try:
        return await run_workflow(
            workflow_id, settings.agent_workspace, settings.project_root, settings
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


@app.get("/v1/users/{user_id}/conversations", response_model=list[ConversationListItem])
async def list_conversations(
    user_id: str,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    repository = ConversationRepository(session)
    conversations = await repository.list_for_user(user_id, max(1, min(limit, 100)))
    items: list[ConversationListItem] = []
    for conversation in conversations:
        messages = await repository.list_messages(conversation.id)
        user_message = next((message for message in messages if message.role == "user"), None)
        preview = messages[-1].content[:120] if messages else ""
        title = user_message.content[:32] if user_message else "新建任务"
        items.append(
            ConversationListItem(
                id=conversation.id,
                user_id=conversation.user_id,
                status=conversation.status,
                created_at=conversation.created_at,
                title=title,
                preview=preview,
                message_count=len(messages),
            )
        )
    return items


@app.get("/v1/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation_detail(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    repository = ConversationRepository(session)
    conversation = await repository.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = await repository.list_messages(conversation_id)
    stored_summary = await repository.latest_summary(conversation_id)
    return ConversationDetail(
        id=conversation.id,
        user_id=conversation.user_id,
        status=conversation.status,
        created_at=conversation.created_at,
        messages=[
            ConversationMessageRead(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
        summary=stored_summary.payload if stored_summary else None,
    )


@app.post("/v1/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_message(
    conversation_id: UUID,
    payload: ChatRequest,
    service: AgentService = Depends(get_agent_service),
):
    try:
        return await service.chat(
            conversation_id,
            payload.content,
            payload.use_web,
            payload.model,
            payload.reasoning_effort,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ConversationFinalizedError as exc:
        raise HTTPException(status_code=409, detail="Conversation is finalized") from exc
    except ResponseError as exc:
        raise model_http_error(exc) from exc
    except (ConnectionError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=503, detail="无法连接本地 Ollama，请重新运行一键启动。"
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="模型响应超时，请选择较小模型或降低调用强度。"
        ) from exc


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
    except ResponseError as exc:
        raise model_http_error(exc) from exc
    except (ConnectionError, httpx.RequestError) as exc:
        raise HTTPException(
            status_code=503, detail="无法连接本地 Ollama，请重新运行一键启动。"
        ) from exc


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


@app.post("/v1/uploads")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
) -> dict[str, str]:
    """Receive a file from the operator and store it under ``workspace/uploads/``.

    The agent can then read it with ``workspace_read`` (``uploads/<filename>``)
    on the next turn. We deliberately keep this endpoint small: it only
    accepts the upload, never lets the browser enumerate the directory, and
    caps the size to ``UPLOAD_MAX_BYTES`` to keep the SQLite database from
    bloating when the operator drags a video into the chat.
    """
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机调用")
    settings = get_settings()
    workspace = Path(settings.agent_workspace).resolve()  # noqa: ASYNC240
    upload_dir = workspace / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Sanitise filename: keep the basename, drop any path components the
    # browser might supply (e.g. C:\fakepath\foo.txt). Fall back to a uuid
    # if the browser sent nothing usable.
    original_name = Path(file.filename or "").name or f"upload-{_uuid4().hex}.bin"
    safe_name = original_name.replace("\x00", "").strip() or f"upload-{_uuid4().hex}.bin"
    destination = (upload_dir / safe_name).resolve()
    if upload_dir not in destination.parents:
        raise HTTPException(status_code=400, detail="文件名非法")
    chunk_size = 1024 * 1024
    written = 0
    with destination.open("wb") as target_file:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            written += len(chunk)
            if written > settings.upload_max_bytes:
                target_file.close()
                destination.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过 {settings.upload_max_bytes // (1024*1024)} MB 限制",
                )
            target_file.write(chunk)
    return {
        "filename": safe_name,
        "bytes": str(written),
        "path": f"uploads/{safe_name}",
        "message": (
            f"已保存到 workspace/uploads/{safe_name}。"
            "Agent 下次工具调用时可用 workspace_read 读取。"
        ),
    }


@app.post("/v1/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    """Gracefully stop the local Agent service.

    Restricted to localhost callers: the endpoint is reachable only when
    the operator has direct access to the machine, and rejecting external
    hosts prevents a remote attacker from killing a user's local agent.
    """
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机调用")
    # Defer the actual exit so the JSON response is flushed to the browser
    # before the uvicorn loop tears down.
    import asyncio
    import sys

    loop = asyncio.get_running_loop()
    loop.call_later(0.3, sys.exit, 0)
    return {"status": "shutting_down", "message": "Agent 将在约 1 秒后停止，关闭此网页即可。"}


@app.get("/v1/debug/proxy-env")
async def debug_proxy_env(request: Request) -> dict[str, str | None]:
    """Return the proxy-related environment variables the running agent sees.

    Useful for diagnosing web-search failures where the local network
    requires a proxy that the agent process did not inherit.
    """
    client_host = (request.client.host if request.client else "") or ""
    if client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="仅允许本机调用")
    import os

    return {
        key: os.environ.get(key)
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "NO_PROXY",
            "no_proxy",
        )
    }
