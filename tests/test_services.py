import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from self_learning_agent.domain import (
    ConversationSummary,
    MemoryCandidate,
    MemoryType,
    MessageRole,
    TranscriptMessage,
)
from self_learning_agent.config import Settings
from self_learning_agent.services import (
    _attach_web_evidence,
    _direct_file_read_answer,
    is_durable_user_statement,
    validate_summary_sources,
)


def test_direct_file_read_handles_directory_and_missing_path(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    file_path = workspace / "README.md"
    file_path.write_text("hello", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        agent_workspace=str(workspace),
        project_root=str(workspace),
        file_access_mode="local",
    )

    file_answer = asyncio.run(_direct_file_read_answer(f"请读取 {file_path}", settings))
    assert file_answer is not None
    assert "hello" in file_answer

    directory_answer = asyncio.run(_direct_file_read_answer(f"请读取 {workspace}", settings))
    assert directory_answer is not None
    assert "README.md" in directory_answer

    missing_answer = asyncio.run(
        _direct_file_read_answer(f"请读取 {workspace / 'missing.txt'}", settings)
    )
    assert missing_answer is not None
    assert "文件读取失败" in missing_answer


def transcript_message() -> TranscriptMessage:
    return TranscriptMessage(
        id=uuid4(),
        role=MessageRole.USER,
        content="I prefer concise answers.",
        created_at=datetime.now(UTC),
    )


def test_summary_candidates_keep_only_real_source_ids() -> None:
    message = transcript_message()
    summary = ConversationSummary(
        synopsis="The user prefers concise answers.",
        candidate_memories=[
            MemoryCandidate(
                content="The user prefers concise answers.",
                memory_type=MemoryType.PREFERENCE,
                confidence=0.95,
                source_message_ids=[message.id, uuid4()],
            )
        ],
    )

    validated = validate_summary_sources(summary, [message])

    assert validated.candidate_memories[0].source_message_ids == [message.id]


def test_summary_does_not_invent_an_episodic_memory() -> None:
    message = transcript_message()
    summary = ConversationSummary(synopsis="The user discussed response style.")

    validated = validate_summary_sources(summary, [message])

    assert all(
        candidate.memory_type != MemoryType.EPISODIC
        for candidate in validated.candidate_memories
    )


def test_non_episodic_memory_cannot_cite_an_assistant_message() -> None:
    assistant_message = transcript_message().model_copy(update={"role": MessageRole.ASSISTANT})
    summary = ConversationSummary(
        synopsis="The assistant supplied an answer.",
        candidate_memories=[
            MemoryCandidate(
                content="An unsupported fact from the assistant.",
                memory_type=MemoryType.SEMANTIC,
                confidence=0.9,
                source_message_ids=[assistant_message.id],
            )
        ],
    )

    validated = validate_summary_sources(summary, [assistant_message])

    assert all(
        candidate.content != "An unsupported fact from the assistant."
        for candidate in validated.candidate_memories
    )


def test_information_request_cannot_source_profile_memory() -> None:
    request = transcript_message().model_copy(
        update={"content": "Give me a list of cricket world cup winners"}
    )
    summary = ConversationSummary(
        synopsis="The user requested cricket information.",
        candidate_memories=[
            MemoryCandidate(
                content="A list of cricket world cup winners.",
                memory_type=MemoryType.SEMANTIC,
                confidence=0.9,
                source_message_ids=[request.id],
            )
        ],
    )

    validated = validate_summary_sources(summary, [request])

    assert all(
        candidate.content != "A list of cricket world cup winners."
        for candidate in validated.candidate_memories
    )


def test_explicit_profile_statements_become_memory_candidates() -> None:
    name_message = transcript_message().model_copy(update={"content": "My name is Dilep"})
    favorite_message = transcript_message().model_copy(
        update={"id": uuid4(), "content": "My fav game is Cricket"}
    )

    validated = validate_summary_sources(
        ConversationSummary(synopsis="The user shared profile information."),
        [name_message, favorite_message],
    )

    assert [candidate.content for candidate in validated.candidate_memories] == [
        "The user's name is Dilep.",
        "The user's favorite game is Cricket.",
    ]


def test_web_evidence_is_visible_when_model_omits_sources() -> None:
    context = "外网搜索结果（DuckDuckGo，请核对来源）：\n1. Example\n   来源：https://example.com"
    answer = _attach_web_evidence("无法确定。", context)
    assert "https://example.com" in answer


def test_failed_web_search_is_not_appended_to_answer() -> None:
    # A failed search context must not be folded into the assistant answer,
    # otherwise small models echo it as if it were real search output.
    failure = "外网搜索失败：DuckDuckGo超时。请稍后重试。"
    timeout = "外网搜索超时（14秒）。请稍后重试。"
    assert _attach_web_evidence("模型给的回复。", failure) == "模型给的回复。"
    assert _attach_web_evidence("模型给的回复。", timeout) == "模型给的回复。"


def test_chinese_full_width_question_is_not_a_durable_statement() -> None:
    # A Chinese full-width question mark closes a sentence the same way as an
    # ASCII question mark; without this guard such content would be written
    # into long-term memory as if it were a user fact.
    assert is_durable_user_statement("你怎么看这个项目？") is False
    assert is_durable_user_statement("How does this work?") is False


def test_durable_chinese_statement_still_passes() -> None:
    assert is_durable_user_statement("我比较喜欢简洁一点的回答") is True
