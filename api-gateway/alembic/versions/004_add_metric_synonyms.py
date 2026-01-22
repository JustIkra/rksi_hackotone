"""Add metric_synonym table.

Revision ID: 004_metric_synonyms
Revises: 003_cascade_category
Create Date: 2025-01-20

Creates metric_synonym table for storing alternative names/aliases
for metrics to improve AI extraction matching.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004_metric_synonyms"
down_revision = "003_cascade_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_synonym",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("metric_def_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("synonym", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["metric_def_id"], ["metric_def.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
        sa.UniqueConstraint("synonym", name="uq_metric_synonym_text"),
    )
    op.create_index(
        "idx_metric_synonym_metric_def", "metric_synonym", ["metric_def_id"]
    )
    op.create_index(
        "idx_metric_synonym_text_lower",
        "metric_synonym",
        [sa.text("LOWER(synonym)")],
    )


def downgrade() -> None:
    op.drop_index("idx_metric_synonym_text_lower", table_name="metric_synonym")
    op.drop_index("idx_metric_synonym_metric_def", table_name="metric_synonym")
    op.drop_table("metric_synonym")
