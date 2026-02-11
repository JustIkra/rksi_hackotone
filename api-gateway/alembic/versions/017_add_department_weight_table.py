"""Add weight_table_id to department.

Revision ID: 017_add_department_weight_table
Revises: 016_add_organizations
Create Date: 2026-02-11

Links a department to a weight table for suitability scoring.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "017_add_department_weight_table"
down_revision = "016_add_organizations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "department",
        sa.Column(
            "weight_table_id",
            UUID(as_uuid=True),
            sa.ForeignKey("weight_table.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_department_weight_table_id", "department", ["weight_table_id"])


def downgrade() -> None:
    op.drop_index("ix_department_weight_table_id", table_name="department")
    op.drop_column("department", "weight_table_id")
