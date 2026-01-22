"""Change metric_def.category_id ondelete from SET NULL to CASCADE.

Revision ID: 003_cascade_category
Revises: 002_metric_categories
Create Date: 2025-01-19

Changes:
- Drop existing FK constraint with ondelete="SET NULL"
- Add new FK constraint with ondelete="CASCADE"

This ensures that when a metric_category is deleted, all related
metric_def records are also deleted (cascading delete).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_cascade_category"
down_revision = "002_metric_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing FK constraint with SET NULL
    op.drop_constraint("fk_metric_def_category", "metric_def", type_="foreignkey")

    # Create new FK constraint with CASCADE
    op.create_foreign_key(
        "fk_metric_def_category",
        "metric_def",
        "metric_category",
        ["category_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Drop CASCADE constraint
    op.drop_constraint("fk_metric_def_category", "metric_def", type_="foreignkey")

    # Restore SET NULL constraint
    op.create_foreign_key(
        "fk_metric_def_category",
        "metric_def",
        "metric_category",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )
