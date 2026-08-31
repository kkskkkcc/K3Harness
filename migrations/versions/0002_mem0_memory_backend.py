"""Move long-term memory ownership to Mem0.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Summaries remain in PostgreSQL for auditability, but embeddings and memory
    # retrieval are now owned by the local Mem0 + Qdrant stack.
    op.alter_column(
        "conversation_summaries",
        "embedding",
        existing_type=Vector(1536),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE conversation_summaries "
        "SET embedding = array_fill(0::real, ARRAY[1536])::vector "
        "WHERE embedding IS NULL"
    )
    op.alter_column(
        "conversation_summaries",
        "embedding",
        existing_type=Vector(1536),
        nullable=False,
    )
