"""Initial schema - all core tables.

Revision ID: 001_initial
Revises:
Create Date: 2025-01-16

Creates all tables from clean state:
- user
- participant
- file_ref
- report
- report_image
- prof_activity
- weight_table
- metric_def
- extracted_metric
- participant_metric
- scoring_result
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User table
    op.create_table(
        "user",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="USER"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("approved_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.CheckConstraint("role IN ('ADMIN', 'USER')", name="user_role_check"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'DISABLED')", name="user_status_check"
        ),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    # Participant table
    op.create_table(
        "participant",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_participant_full_name", "participant", ["full_name"])
    op.create_index("ix_participant_external_id", "participant", ["external_id"])

    # FileRef table
    op.create_table(
        "file_ref",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage", sa.String(20), nullable=False, server_default="LOCAL"),
        sa.Column("bucket", sa.String(100), nullable=False),
        sa.Column("key", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage", "bucket", "key", name="file_ref_location_unique"),
        sa.CheckConstraint("storage IN ('LOCAL', 'MINIO')", name="file_ref_storage_check"),
        sa.CheckConstraint("size_bytes >= 0", name="file_ref_size_check"),
    )
    op.create_index("idx_file_ref_storage", "file_ref", ["storage"])

    # Report table
    op.create_table(
        "report",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="UPLOADED"),
        sa.Column("file_ref_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("extracted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("extract_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participant.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["file_ref_id"], ["file_ref.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'EXTRACTED', 'FAILED')",
            name="report_status_check",
        ),
    )
    op.create_index("idx_report_status", "report", ["status"])
    op.create_index("idx_report_participant", "report", ["participant_id"])

    # ReportImage table
    op.create_table(
        "report_image",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="TABLE"),
        sa.Column("file_ref_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_ref_id"], ["file_ref.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "report_id", "page", "order_index", name="report_image_order_unique"
        ),
        sa.CheckConstraint("kind IN ('TABLE', 'OTHER')", name="report_image_kind_check"),
        sa.CheckConstraint("page >= 0", name="report_image_page_check"),
        sa.CheckConstraint("order_index >= 0", name="report_image_order_check"),
    )
    op.create_index("idx_report_image_report", "report_image", ["report_id"])

    # ProfActivity table
    op.create_table(
        "prof_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_prof_activity_code", "prof_activity", ["code"], unique=True)

    # WeightTable table
    op.create_table(
        "weight_table",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prof_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["prof_activity_id"], ["prof_activity.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("prof_activity_id", name="uq_weight_table_prof_activity"),
    )

    # MetricDef table
    op.create_table(
        "metric_def",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_ru", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("min_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_value", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.CheckConstraint(
            "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
            name="metric_def_range_check",
        ),
    )
    op.create_index("ix_metric_def_code", "metric_def", ["code"], unique=True)
    op.create_index("ix_metric_def_active", "metric_def", ["active"])

    # ExtractedMetric table
    op.create_table(
        "extracted_metric",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_def_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="OCR"),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["metric_def_id"], ["metric_def.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "report_id", "metric_def_id", name="extracted_metric_report_metric_unique"
        ),
        sa.CheckConstraint(
            "source IN ('OCR', 'LLM', 'MANUAL')", name="extracted_metric_source_check"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="extracted_metric_confidence_check",
        ),
    )
    op.create_index("ix_extracted_metric_report_id", "extracted_metric", ["report_id"])
    op.create_index(
        "ix_extracted_metric_metric_def_id", "extracted_metric", ["metric_def_id"]
    )

    # ParticipantMetric table
    op.create_table(
        "participant_metric",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_code", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(4, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("last_source_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participant.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_source_report_id"], ["report.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "participant_id", "metric_code", name="participant_metric_unique"
        ),
        sa.CheckConstraint(
            "value >= 1 AND value <= 10", name="participant_metric_value_range_check"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="participant_metric_confidence_check",
        ),
    )
    op.create_index(
        "ix_participant_metric_participant_id", "participant_metric", ["participant_id"]
    )
    op.create_index(
        "ix_participant_metric_metric_code", "participant_metric", ["metric_code"]
    )

    # ScoringResult table
    op.create_table(
        "scoring_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("weight_table_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dev_areas", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "computed_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("compute_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["participant_id"], ["participant.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["weight_table_id"], ["weight_table.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "score_pct >= 0 AND score_pct <= 100", name="scoring_result_score_range_check"
        ),
    )
    op.create_index(
        "ix_scoring_result_participant_id", "scoring_result", ["participant_id"]
    )
    op.create_index("ix_scoring_result_computed_at", "scoring_result", ["computed_at"])
    op.create_index(
        "ix_scoring_result_participant_computed",
        "scoring_result",
        ["participant_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_table("scoring_result")
    op.drop_table("participant_metric")
    op.drop_table("extracted_metric")
    op.drop_table("metric_def")
    op.drop_table("weight_table")
    op.drop_table("prof_activity")
    op.drop_table("report_image")
    op.drop_table("report")
    op.drop_table("file_ref")
    op.drop_table("participant")
    op.drop_table("user")
