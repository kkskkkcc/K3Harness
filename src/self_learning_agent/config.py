from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Self-Learning AI Agent"
    app_env: Literal["development", "test", "production"] = "development"
    # SQLite is the portable default. Set DATABASE_URL to PostgreSQL when a
    # shared production database is available.
    database_url: str = "sqlite+aiosqlite:///./data/agent.db"

    memory_backend: Literal["local", "mem0"] = "local"
    # ``agent_workspace`` is the directory the agent can both read and write;
    # it is also the default landing spot for user-uploaded files.
    # ``project_root`` is the wider trust boundary: the agent can read
    # project-level documents (README, project briefs, configuration) without
    # being able to escape outside the project. On K3 the deployer sets
    # both to the on-device path.
    agent_workspace: str = "./workspace"
    project_root: str = "."
    file_access_mode: Literal["local", "project"] = "local"
    upload_max_bytes: int = 20 * 1024 * 1024
    context_char_budget: int = 18000
    max_tool_steps: int = 4
    latency_target_seconds: float = 9.5
    response_timeout_seconds: float = 120.0
    tool_timeout_seconds: float = 3.0
    hardware_enabled: bool = False
    hardware_mode: Literal["simulated", "k3"] = "simulated"
    camera_backend: Literal["none", "opencv", "gstreamer"] = "none"
    yolo_model_path: str = "./models/yolo"

    # K3 ships an optimized llama-server instead of Ollama.  The OpenAI
    # compatible backend keeps the same model/profile/tool API while allowing
    # the runtime to point at llama-server (or another compatible endpoint).
    llm_backend: Literal["ollama", "openai_compatible"] = "ollama"
    llm_base_url: str = ""
    llm_api_key: str = ""

    ollama_base_url: str = "http://localhost:11434"
    # The local GGUF profiles are imported into Ollama as qwen3-local:*.
    # 8B is the speed/quality default for the K3 migration target.
    ollama_chat_model: str = "qwen3-local:8b"
    ollama_summary_model: str = "qwen3-local:8b"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dimensions: int = 768
    ollama_disable_thinking: bool = False
    ollama_chat_max_tokens: int = 512
    ollama_summary_max_tokens: int = 350
    ollama_keep_alive: str = "2m"

    # Opt-in proxy for web search. Empty string means the search code does
    # NOT honour ``HTTP_PROXY`` / ``HTTPS_PROXY`` from the environment: that
    # decoupling matters on developer machines where a local proxy tool (e.g.
    # Mihomo / Clash) is running but its rule set rejects our target hosts,
    # and on the K3 board where the deployment may run on a closed network.
    web_search_proxy: str = ""

    mem0_qdrant_host: str = "localhost"
    mem0_qdrant_port: int = 6333
    mem0_qdrant_collection: str = "self_learning_agent_memories"
    mem0_history_db_path: str = ".data/mem0_history.db"
    mem0_telemetry: bool = False

    recent_message_limit: int = 8
    memory_retrieval_limit: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
