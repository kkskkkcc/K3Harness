from datetime import UTC, datetime
from uuid import uuid4

from self_learning_agent.domain import (
    ConversationSummary,
    MemoryCandidate,
    MemoryType,
    MessageRole,
    TranscriptMessage,
)
from self_learning_agent.services import validate_summary_sources


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
