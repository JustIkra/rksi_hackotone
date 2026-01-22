"""Change extracted_metric.metric_def_id ondelete from RESTRICT to CASCADE.

Revision ID: 005_cascade_extracted_metric
Revises: 004_metric_synonyms
Create Date: 2026-01-20

Changes:
- Drop existing FK constraint with ondelete="RESTRICT"
- Add new FK constraint with ondelete="CASCADE"

This ensures that when a metric_def is deleted, all related
extracted_metric records are also deleted (cascading delete).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "005_cascade_extracted_metric"
down_revision = "004_metric_synonyms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing FK constraint with RESTRICT
    op.drop_constraint(
        "extracted_metric_metric_def_id_fkey", "extracted_metric", type_="foreignkey"
    )

    # Create new FK constraint with CASCADE
    op.create_foreign_key(
        "extracted_metric_metric_def_id_fkey",
        "extracted_metric",
        "metric_def",
        ["metric_def_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Drop CASCADE constraint
    op.drop_constraint(
        "extracted_metric_metric_def_id_fkey", "extracted_metric", type_="foreignkey"
    )

    # Restore RESTRICT constraint
    op.create_foreign_key(
        "extracted_metric_metric_def_id_fkey",
        "extracted_metric",
        "metric_def",
        ["metric_def_id"],
        ["id"],
        ondelete="RESTRICT",
    )
