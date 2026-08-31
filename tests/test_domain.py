from uuid import uuid4

import pytest
from pydantic import ValidationError

from self_learning_agent.domain import MemoryCandidate, MemoryType


def test_memory_candidate_requires_source_provenance() -> None:
    with pytest.raises(ValidationError):
        MemoryCandidate(
            content="The user prefers concise answers.",
            memory_type=MemoryType.PREFERENCE,
            confidence=0.9,
            source_message_ids=[],
        )


def test_memory_candidate_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        MemoryCandidate(
            content="The user prefers concise answers.",
            memory_type=MemoryType.PREFERENCE,
            confidence=1.1,
            source_message_ids=[uuid4()],
        )
