"""Add metric_audit_log table for tracking metric operations.

Revision ID: 007_metric_audit_log
Revises: 006_needs_review
Create Date: 2026-01-20

Adds metric_audit_log table for audit logging of metric-related operations
(bulk_delete, delete, etc.) with affected counts and user tracking.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_metric_audit_log"
down_revision = "006_needs_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("metric_codes", sa.ARRAY(sa.String(50)), nullable=False),
        sa.Column("affected_counts", postgresql.JSONB(), nullable=True),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_metric_audit_log_timestamp", "metric_audit_log", ["timestamp"]
    )
    op.create_index(
        "ix_metric_audit_log_action", "metric_audit_log", ["action"]
    )


def downgrade() -> None:
    op.drop_index("ix_metric_audit_log_action", table_name="metric_audit_log")
    op.drop_index("ix_metric_audit_log_timestamp", table_name="metric_audit_log")
    op.drop_table("metric_audit_log")
