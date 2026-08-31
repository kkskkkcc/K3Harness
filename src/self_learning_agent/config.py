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
    database_url: str = "postgresql+asyncpg://agent:agent@localhost:5432/agent_memory"

    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "qwen3:1.7b"
    ollama_summary_model: str = "qwen3:1.7b"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_embedding_dimensions: int = 768
    ollama_disable_thinking: bool = True
    ollama_chat_max_tokens: int = 512
    ollama_summary_max_tokens: int = 350
    ollama_keep_alive: str = "2m"

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
