"""Add metric_embedding table with pgvector for semantic metric matching.

Revision ID: 009_metric_embedding_pgvector
Revises: 008_moderation_status
Create Date: 2026-01-22

Creates metric_embedding table for storing vector embeddings of metric definitions.
Used for semantic similarity search to match extracted metric names to canonical definitions.

Features:
- pgvector extension for vector operations
- Vector(1536) column for text-embedding-3-small embeddings
- IVFFlat index for efficient cosine similarity search
- Unique constraint: one embedding per metric_def
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "009_metric_embedding_pgvector"
down_revision = "008_moderation_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create metric_embedding table with vector column
    # Using raw SQL because SQLAlchemy doesn't natively support pgvector types
    op.execute(
        """
        CREATE TABLE metric_embedding (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            metric_def_id UUID NOT NULL
                REFERENCES metric_def(id) ON DELETE CASCADE,
            embedding vector(1536) NOT NULL,
            indexed_text TEXT NOT NULL,
            model VARCHAR(100) NOT NULL,
            indexed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_metric_embedding_metric_def UNIQUE (metric_def_id)
        )
        """
    )

    # Create index for metric_def_id lookups
    op.execute(
        """
        CREATE INDEX ix_metric_embedding_metric_def_id
        ON metric_embedding (metric_def_id)
        """
    )

    # Create HNSW index for cosine similarity search
    # 1536 dimensions fits within pgvector's 2000 dim limit
    op.execute(
        """
        CREATE INDEX idx_metric_embedding_vector
        ON metric_embedding USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_metric_embedding_vector")
    op.execute("DROP INDEX IF EXISTS ix_metric_embedding_metric_def_id")

    # Drop the table
    op.execute("DROP TABLE IF EXISTS metric_embedding")

    # Drop pgvector extension
    # Note: This may fail if other tables use vector types.
    # In that case, the extension should be kept.
    op.execute("DROP EXTENSION IF EXISTS vector")
