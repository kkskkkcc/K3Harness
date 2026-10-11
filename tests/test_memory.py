from pathlib import Path
from uuid import uuid4

from self_learning_agent.config import Settings
from self_learning_agent.domain import (
    ConversationSummary,
    MemoryAction,
    MemoryCandidate,
    MemoryType,
)
from self_learning_agent.memory import (
    build_mem0_config,
    count_memory_actions,
    format_summary_for_memory,
)


def test_mem0_actions_are_normalized_for_the_api() -> None:
    payload = {
        "results": [
            {"event": "ADD"},
            {"event": "UPDATE"},
            {"event": "DELETE"},
            {"event": "NONE"},
        ]
    }

    assert count_memory_actions(payload) == {
        MemoryAction.ADD: 1,
        MemoryAction.UPDATE: 1,
        MemoryAction.DELETE: 1,
        MemoryAction.NO_CHANGE: 1,
    }


def test_mem0_receives_the_summary_and_validated_candidates() -> None:
    summary = ConversationSummary(
        synopsis="The user is building a local AI agent.",
        user_goals=["Build a resume project"],
        candidate_memories=[
            MemoryCandidate(
                content="The user wants a zero-cost local stack.",
                memory_type=MemoryType.PREFERENCE,
                confidence=0.95,
                source_message_ids=[uuid4()],
            )
        ],
    )

    rendered = format_summary_for_memory(summary)

    assert "zero-cost local stack" in rendered
    assert "Build a resume project" not in rendered


def test_mem0_config_uses_only_local_providers() -> None:
    config = build_mem0_config(Settings(_env_file=None), Path(".data/history.db"))

    assert config["llm"]["provider"] == "ollama"
    assert config["llm"]["config"]["model"] == "qwen3-local:8b"
    assert config["llm"]["config"]["max_tokens"] == 350
    assert config["embedder"]["provider"] == "ollama"
    assert config["vector_store"]["provider"] == "qdrant"
