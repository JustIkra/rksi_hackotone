"""
SQLAlchemy ORM models for core tables.

Implements the database schema for users, participants, files, reports, and professional activities.
Based on data-model.md ER diagram.
"""

import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Fallback for environments without pgvector installed
    Vector = None

from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# User Table
class User(Base):
    """
    User account for authentication and authorization.

    Roles:
    - ADMIN: Can approve users, upload weight tables, manage system
    - USER: Can view/upload reports for participants

    Status:
    - PENDING: Awaiting admin approval
    - ACTIVE: Approved and can access system
    - DISABLED: Account disabled
    """

    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    approved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'USER')", name="user_role_check"),
        CheckConstraint("status IN ('PENDING', 'ACTIVE', 'DISABLED')", name="user_status_check"),
    )

    @property
    def display_name(self) -> str:
        """Return full_name if set, otherwise email."""
        return self.full_name if self.full_name else self.email

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role}, status={self.status})>"


# Participant Table
class Participant(Base):
    """
    Participant in proficiency assessment.

    Represents an individual whose competencies are being assessed.
    """

    __tablename__ = "participant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    # Relationships
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="participant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Participant(id={self.id}, full_name={self.full_name})>"


# FileRef Table
class FileRef(Base):
    """
    Reference to a file in storage (LOCAL or MINIO).

    Provides abstraction over storage backend.
    For LOCAL: bucket="local", key="reports/{participant_id}/{report_id}/original.docx"
    For MINIO: bucket="reports", key="{participant_id}/{report_id}/original.docx"
    """

    __tablename__ = "file_ref"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    storage: Mapped[str] = mapped_column(String(20), nullable=False, default="LOCAL")
    bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("storage IN ('LOCAL', 'MINIO')", name="file_ref_storage_check"),
        CheckConstraint("size_bytes >= 0", name="file_ref_size_check"),
        # Unique constraint on (storage, bucket, key) to prevent duplicates
        UniqueConstraint("storage", "bucket", "key", name="file_ref_location_unique"),
        # Index for faster lookups by storage type
        Index("idx_file_ref_storage", "storage"),
    )

    def __repr__(self) -> str:
        return (
            f"<FileRef(id={self.id}, storage={self.storage}, bucket={self.bucket}, key={self.key})>"
        )


# Report Table
class Report(Base):
    """
    Report uploaded for a participant.

    Status:
    - UPLOADED: File uploaded, extraction not started
    - PROCESSING: Extraction in progress
    - EXTRACTED: Metrics extracted successfully
    - FAILED: Extraction failed
    """

    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participant.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOADED")
    file_ref_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_ref.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    extracted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    extract_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extract_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    extract_warning_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    participant: Mapped["Participant"] = relationship("Participant", back_populates="reports")
    file_ref: Mapped["FileRef"] = relationship("FileRef")
    extracted_metrics: Mapped[list["ExtractedMetric"]] = relationship(
        "ExtractedMetric", back_populates="report", cascade="all, delete-orphan"
    )
    images: Mapped[list["ReportImage"]] = relationship(
        "ReportImage", back_populates="report", cascade="all, delete-orphan", order_by="ReportImage.order_index"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('UPLOADED', 'PROCESSING', 'EXTRACTED', 'FAILED')", name="report_status_check"
        ),
        # Index for filtering by status
        Index("idx_report_status", "status"),
        # Index for participant lookup
        Index("idx_report_participant", "participant_id"),
    )

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, participant_id={self.participant_id}, status={self.status})>"


# ReportImage Table
class ReportImage(Base):
    """
    Image extracted from a report document.

    Kinds:
    - TABLE: Image contains a table with metrics
    - OTHER: Other types of images (charts, diagrams, etc.)

    Used for OCR/Vision processing pipeline.
    """

    __tablename__ = "report_image"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="TABLE")
    file_ref_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_ref.id", ondelete="RESTRICT"), nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="images")
    file_ref: Mapped["FileRef"] = relationship("FileRef")

    # Constraints
    __table_args__ = (
        CheckConstraint("kind IN ('TABLE', 'OTHER')", name="report_image_kind_check"),
        CheckConstraint("page >= 0", name="report_image_page_check"),
        CheckConstraint("order_index >= 0", name="report_image_order_check"),
        # Index for filtering by report
        Index("idx_report_image_report", "report_id"),
        # Unique constraint for ordering within a report
        UniqueConstraint("report_id", "page", "order_index", name="report_image_order_unique"),
    )

    def __repr__(self) -> str:
        return f"<ReportImage(id={self.id}, report_id={self.report_id}, kind={self.kind}, page={self.page})>"


# ProfActivity Table
class ProfActivity(Base):
    """
    Professional activity (профессиональная область).

    Represents a professional domain for which competencies are assessed.
    Examples: "developer", "analyst", "manager"
    """

    __tablename__ = "prof_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_tables: Mapped[list["WeightTable"]] = relationship(
        "WeightTable",
        back_populates="prof_activity",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProfActivity(id={self.id}, code={self.code}, name={self.name})>"


# WeightTable Table
class WeightTable(Base):
    """
    Weight table for a professional activity.

    Stores metric weights as JSON structure.
    One weight table per professional activity (no versioning).
    """

    __tablename__ = "weight_table"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prof_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prof_activity.id", ondelete="CASCADE"),
        nullable=False,
    )
    weights: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    prof_activity: Mapped["ProfActivity"] = relationship(
        "ProfActivity", back_populates="weight_tables"
    )

    __table_args__ = (
        UniqueConstraint(
            "prof_activity_id",
            name="uq_weight_table_prof_activity",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<WeightTable(id={self.id}, prof_activity_id={self.prof_activity_id})>"
        )


# MetricCategory Table
class MetricCategory(Base):
    """
    Category for grouping metric definitions.

    Used to organize metrics into logical groups for display and management.
    Examples: "cognitive", "physical", "professional"
    """

    __tablename__ = "metric_category"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    metrics: Mapped[list["MetricDef"]] = relationship(
        "MetricDef", back_populates="category", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="metric_category_sort_order_check"),
        Index("ix_metric_category_sort_order", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<MetricCategory(id={self.id}, code={self.code}, name={self.name})>"


# MetricDef Table
class MetricDef(Base):
    """
    Metric definition (словарь метрик).

    Defines available metrics with validation ranges and metadata.
    Used for both extraction validation and scoring calculations.

    Moderation statuses:
    - APPROVED: Metric is approved and active (default for manually created)
    - PENDING: Metric generated by AI, awaiting admin moderation
    - REJECTED: Metric rejected by admin during moderation
    """

    __tablename__ = "metric_def"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    min_value: Mapped[float | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    max_value: Mapped[float | None] = mapped_column(sa.Numeric(10, 2), nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metric_category.id", ondelete="CASCADE"),
        nullable=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    moderation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="APPROVED", server_default=text("'APPROVED'")
    )
    ai_rationale: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="AI extraction rationale (quotes, page_numbers, confidence)"
    )
    canonical_metric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metric_def.id", ondelete="SET NULL"),
        nullable=True,
        comment="Reference to canonical metric if this is an alias",
    )

    # Relationships
    extracted_metrics: Mapped[list["ExtractedMetric"]] = relationship(
        "ExtractedMetric",
        back_populates="metric_def",
        cascade="all, delete-orphan",
    )
    category: Mapped["MetricCategory | None"] = relationship(
        "MetricCategory", back_populates="metrics"
    )
    synonyms: Mapped[list["MetricSynonym"]] = relationship(
        "MetricSynonym", back_populates="metric_def", cascade="all, delete-orphan"
    )
    embedding: Mapped["MetricEmbedding | None"] = relationship(
        "MetricEmbedding", back_populates="metric_def", uselist=False, cascade="all, delete-orphan"
    )
    canonical_metric: Mapped["MetricDef | None"] = relationship(
        "MetricDef",
        remote_side="MetricDef.id",
        foreign_keys=[canonical_metric_id],
        backref="aliases",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
            name="metric_def_range_check",
        ),
        CheckConstraint("sort_order >= 0", name="metric_def_sort_order_check"),
        CheckConstraint(
            "moderation_status IN ('APPROVED', 'PENDING', 'REJECTED')",
            name="metric_def_moderation_status_check",
        ),
        Index("ix_metric_def_active", "active"),
        Index("ix_metric_def_category_id", "category_id"),
        Index("ix_metric_def_sort_order", "sort_order"),
        Index("ix_metric_def_moderation_status", "moderation_status"),
    )

    def __repr__(self) -> str:
        return f"<MetricDef(id={self.id}, code={self.code}, name={self.name})>"


# MetricSynonym Table
class MetricSynonym(Base):
    """
    Synonym for a metric definition.

    Allows mapping alternative names to canonical metric definitions.
    Used for automatic recognition of metrics from various report formats.

    Constraints:
    - Each synonym must be globally unique (1 synonym = 1 metric_def)
    - CASCADE DELETE when parent metric_def is deleted
    """

    __tablename__ = "metric_synonym"

    id: Mapped[int] = mapped_column(primary_key=True)
    metric_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metric_def.id", ondelete="CASCADE"),
        nullable=False,
    )
    synonym: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )

    # Relationships
    metric_def: Mapped["MetricDef"] = relationship("MetricDef", back_populates="synonyms")
    created_by: Mapped["User | None"] = relationship("User")

    # Constraints
    __table_args__ = (
        Index("idx_metric_synonym_metric_def", "metric_def_id"),
        Index("idx_metric_synonym_text_lower", text("LOWER(synonym)")),
    )

    def __repr__(self) -> str:
        return f"<MetricSynonym(id={self.id}, metric_def_id={self.metric_def_id}, synonym={self.synonym})>"


# ExtractedMetric Table
class ExtractedMetric(Base):
    """
    Extracted metric value from a report.

    Stores numerical values extracted from report images via LLM or manual input.
    Each (report_id, metric_def_id) pair is unique to prevent duplicates.

    Source types:
    - LLM: Extracted via Gemini Vision
    - MANUAL: Manually entered by user
    """

    __tablename__ = "extracted_metric"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    metric_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metric_def.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(sa.Numeric(10, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="OCR")
    confidence: Mapped[float | None] = mapped_column(sa.Numeric(3, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="extracted_metrics")
    metric_def: Mapped["MetricDef"] = relationship("MetricDef", back_populates="extracted_metrics")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "metric_def_id",
            name="extracted_metric_report_metric_unique",
        ),
        CheckConstraint(
            "source IN ('OCR', 'LLM', 'MANUAL')",
            name="extracted_metric_source_check",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="extracted_metric_confidence_check",
        ),
        Index("ix_extracted_metric_report_id", "report_id"),
        Index("ix_extracted_metric_metric_def_id", "metric_def_id"),
    )

    def __repr__(self) -> str:
        return f"<ExtractedMetric(id={self.id}, report_id={self.report_id}, metric_def_id={self.metric_def_id}, value={self.value})>"


# ParticipantMetric Table
class ParticipantMetric(Base):
    """
    Actual metric value for a participant (independent of reports).

    Stores the latest confirmed value for each (participant_id, metric_code) pair.
    When a new report is uploaded with the same metric, this record is updated via upsert
    using deterministic "best result" priority.

    Priority rules:
    - Higher metric value takes precedence
    - On tie, higher confidence is preferred (NULL treated as 0)
    - On tie, more recent report.uploaded_at takes precedence
    """

    __tablename__ = "participant_metric"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participant.id", ondelete="CASCADE"), nullable=False
    )
    metric_code: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(sa.Numeric(4, 2), nullable=False)
    confidence: Mapped[float | None] = mapped_column(sa.Numeric(4, 3), nullable=True)
    last_source_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    participant: Mapped["Participant"] = relationship("Participant")
    last_source_report: Mapped["Report | None"] = relationship("Report")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "metric_code",
            name="participant_metric_unique",
        ),
        CheckConstraint(
            "value >= 1 AND value <= 10",
            name="participant_metric_value_range_check",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="participant_metric_confidence_check",
        ),
        Index("ix_participant_metric_participant_id", "participant_id"),
        Index("ix_participant_metric_metric_code", "metric_code"),
    )

    def __repr__(self) -> str:
        return f"<ParticipantMetric(id={self.id}, participant_id={self.participant_id}, metric_code={self.metric_code}, value={self.value})>"


# ScoringResult Table
class ScoringResult(Base):
    """
    Scoring result for a participant's professional fitness assessment.

    Stores calculated scores, weight table version, and optional analysis data.
    History is preserved - multiple results can exist for the same participant.

    Fields:
    - score_pct: Calculated percentage score (0-100), quantized to 0.01
    - strengths: JSONB array of top-performing metrics
    - dev_areas: JSONB array of development areas (low-scoring metrics)
    """

    __tablename__ = "scoring_result"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participant.id", ondelete="CASCADE"), nullable=False
    )
    weight_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weight_table.id", ondelete="RESTRICT"), nullable=False
    )
    score_pct: Mapped[float] = mapped_column(sa.Numeric(5, 2), nullable=False)
    strengths: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    dev_areas: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    compute_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    participant: Mapped["Participant"] = relationship("Participant")
    weight_table: Mapped["WeightTable"] = relationship("WeightTable")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "score_pct >= 0 AND score_pct <= 100",
            name="scoring_result_score_range_check",
        ),
        Index("ix_scoring_result_participant_id", "participant_id"),
        Index("ix_scoring_result_computed_at", "computed_at"),
        Index(
            "ix_scoring_result_participant_computed",
            "participant_id",
            "computed_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<ScoringResult(id={self.id}, participant_id={self.participant_id}, score_pct={self.score_pct})>"


# MetricAuditLog Table
class MetricAuditLog(Base):
    """
    Audit log for metric-related operations.

    Records bulk delete operations and other administrative actions on metrics.
    Used for compliance, debugging, and administrative review.

    Fields:
    - action: Type of action performed (e.g., "bulk_delete", "delete")
    - metric_codes: List of metric codes affected by the action
    - affected_counts: JSONB with counts of cascaded deletes per table
    """

    __tablename__ = "metric_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_codes: Mapped[list[str]] = mapped_column(sa.ARRAY(String(50)), nullable=False)
    affected_counts: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    user: Mapped["User | None"] = relationship("User")

    # Constraints
    __table_args__ = (
        Index("ix_metric_audit_log_timestamp", "timestamp"),
        Index("ix_metric_audit_log_action", "action"),
    )

    def __repr__(self) -> str:
        return f"<MetricAuditLog(id={self.id}, action={self.action}, timestamp={self.timestamp})>"


# MetricEmbedding Table
class MetricEmbedding(Base):
    """
    Vector embedding for semantic metric search.

    Stores embeddings generated from metric names, descriptions, and synonyms
    for similarity-based matching of extracted metrics to canonical definitions.

    Uses pgvector extension with IVFFlat indexing for efficient cosine similarity search.
    One embedding per metric_def (updated when metric changes).
    """

    __tablename__ = "metric_embedding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    metric_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("metric_def.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Vector column - 1536 dimensions for text-embedding-3-small
    # Using raw SQL type annotation since pgvector may not be installed in all envs
    embedding = mapped_column(
        Vector(1536) if Vector else Text,
        nullable=False,
    )
    indexed_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    metric_def: Mapped["MetricDef"] = relationship("MetricDef", back_populates="embedding")

    # Constraints
    __table_args__ = (
        Index("ix_metric_embedding_metric_def_id", "metric_def_id"),
    )

    def __repr__(self) -> str:
        return f"<MetricEmbedding(id={self.id}, metric_def_id={self.metric_def_id}, model={self.model})>"
