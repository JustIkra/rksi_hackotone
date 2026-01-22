"""Add needs_review column to weight_table.

Revision ID: 006_needs_review
Revises: 005_cascade_extracted_metric
Create Date: 2026-01-20

Adds needs_review boolean flag to weight_table for tracking when weights
need manual adjustment (e.g., when a metric is deleted and weight sum
no longer equals 1.0).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "006_needs_review"
down_revision = "005_cascade_extracted_metric"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "weight_table",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("weight_table", "needs_review")
