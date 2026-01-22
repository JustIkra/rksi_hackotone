"""Add metric_category table and update metric_def.

Revision ID: 002_metric_categories
Revises: 001_initial
Create Date: 2025-01-18

Adds:
- metric_category table for organizing metrics
- category_id and sort_order columns to metric_def
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_metric_categories"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create metric_category table
    op.create_table(
        "metric_category",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint("sort_order >= 0", name="metric_category_sort_order_check"),
    )
    op.create_index("ix_metric_category_code", "metric_category", ["code"], unique=True)
    op.create_index("ix_metric_category_sort_order", "metric_category", ["sort_order"])

    # Add category_id and sort_order to metric_def
    op.add_column(
        "metric_def",
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "metric_def",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Add foreign key constraint
    op.create_foreign_key(
        "fk_metric_def_category",
        "metric_def",
        "metric_category",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index for category_id
    op.create_index("ix_metric_def_category_id", "metric_def", ["category_id"])

    # Add check constraint for sort_order
    op.create_check_constraint(
        "metric_def_sort_order_check", "metric_def", "sort_order >= 0"
    )


def downgrade() -> None:
    # Remove constraints and columns from metric_def
    op.drop_constraint("metric_def_sort_order_check", "metric_def", type_="check")
    op.drop_index("ix_metric_def_category_id", table_name="metric_def")
    op.drop_constraint("fk_metric_def_category", "metric_def", type_="foreignkey")
    op.drop_column("metric_def", "sort_order")
    op.drop_column("metric_def", "category_id")

    # Drop metric_category table
    op.drop_index("ix_metric_category_sort_order", table_name="metric_category")
    op.drop_index("ix_metric_category_code", table_name="metric_category")
    op.drop_table("metric_category")
