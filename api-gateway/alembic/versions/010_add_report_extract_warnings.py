"""Add extract_warning and extract_warning_details columns to report table.

Revision ID: 010_add_report_extract_warnings
Revises: 009_metric_embedding_pgvector
Create Date: 2026-01-29

Adds fields to store extraction warnings when the extraction succeeds
but with partial results or validation issues.

Fields:
- extract_warning: Short warning message (e.g., "partial_extraction")
- extract_warning_details: JSONB with detailed warning information
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "010_add_report_extract_warnings"
down_revision = "009_metric_embedding_pgvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report", sa.Column("extract_warning", sa.Text(), nullable=True))
    op.add_column(
        "report",
        sa.Column("extract_warning_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("report", "extract_warning_details")
    op.drop_column("report", "extract_warning")
