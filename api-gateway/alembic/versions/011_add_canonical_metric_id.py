"""Add canonical_metric_id to metric_def for alias/canonical relationship.

Revision ID: 011_add_canonical_metric_id
Revises: 010_add_report_extract_warnings
Create Date: 2026-01-30

Adds a self-referential foreign key to metric_def table to support
canonical metric relationships. This allows marking metrics as aliases
of a canonical metric, enabling deduplication of semantically identical
metrics created during AI extraction.

When a metric has canonical_metric_id set:
- It is considered an alias of the canonical metric
- The alias is typically deactivated (active=False)
- ParticipantMetric records should use the canonical metric code
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "011_add_canonical_metric_id"
down_revision = "010_add_report_extract_warnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add canonical_metric_id column with self-referential FK
    op.add_column(
        "metric_def",
        sa.Column(
            "canonical_metric_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_metric_def_canonical_metric_id",
        "metric_def",
        "metric_def",
        ["canonical_metric_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_metric_def_canonical",
        "metric_def",
        ["canonical_metric_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_def_canonical", table_name="metric_def")
    op.drop_constraint("fk_metric_def_canonical_metric_id", "metric_def", type_="foreignkey")
    op.drop_column("metric_def", "canonical_metric_id")
