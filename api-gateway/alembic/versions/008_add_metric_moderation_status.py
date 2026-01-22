"""Add moderation_status and ai_rationale to metric_def.

Revision ID: 008_moderation_status
Revises: 007_metric_audit_log
Create Date: 2026-01-20

Adds moderation support for AI-generated metrics:
- moderation_status: APPROVED (default), PENDING, REJECTED
- ai_rationale: JSONB for AI extraction reasoning (quotes, confidence, etc.)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "008_moderation_status"
down_revision = "007_metric_audit_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add moderation_status column with default APPROVED
    op.add_column(
        "metric_def",
        sa.Column(
            "moderation_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'APPROVED'"),
        ),
    )

    # Add ai_rationale JSONB column for AI extraction metadata
    op.add_column(
        "metric_def",
        sa.Column(
            "ai_rationale",
            postgresql.JSONB(),
            nullable=True,
            comment="AI extraction rationale (quotes, page_numbers, confidence)",
        ),
    )

    # Add check constraint for moderation_status values
    op.create_check_constraint(
        "metric_def_moderation_status_check",
        "metric_def",
        "moderation_status IN ('APPROVED', 'PENDING', 'REJECTED')",
    )

    # Add index for filtering by moderation status
    op.create_index(
        "ix_metric_def_moderation_status",
        "metric_def",
        ["moderation_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_metric_def_moderation_status", table_name="metric_def")
    op.drop_constraint(
        "metric_def_moderation_status_check", "metric_def", type_="check"
    )
    op.drop_column("metric_def", "ai_rationale")
    op.drop_column("metric_def", "moderation_status")
