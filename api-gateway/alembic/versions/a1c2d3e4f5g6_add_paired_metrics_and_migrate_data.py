"""add_paired_metrics_and_migrate_data

Revision ID: a1c2d3e4f5g6
Revises: fab71e120eda
Create Date: 2025-12-16 17:00:00.000000

Adds paired metric definitions and migrates existing single-pole metrics
to the new paired format (e.g., ЗАМКНУТОСТЬ + ОБЩИТЕЛЬНОСТЬ → ЗАМКНУТОСТЬ–ОБЩИТЕЛЬНОСТЬ).
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

from app.services.metric_localization import METRIC_DISPLAY_NAMES_RU, PAIRED_METRICS


# revision identifiers, used by Alembic.
revision: str = 'a1c2d3e4f5g6'
down_revision: Union[str, None] = 'fab71e120eda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mapping of paired code -> (left_code, right_code)
PAIRED_TO_SINGLE: dict[str, tuple[str, str]] = {
    "introversion_sociability": ("introversion", "sociability"),
    "passivity_activity": ("passivity", "activity"),
    "distrust_friendliness": ("distrust", "friendliness"),
    "independence_conformism": ("independence", "conformism"),
    "moral_flexibility_morality": ("moral_flexibility", "morality"),
    "impulsiveness_organization": ("impulsiveness", "organization"),
    "anxiety_stability": ("anxiety", "emotional_stability"),
    "sensitivity_insensitivity": ("sensitivity", "insensitivity"),
    "intellectual_restraint_curiosity": ("intellectual_restraint", "curiosity"),
    "traditionality_originality": ("traditionality", "originality"),
    "concreteness_abstractness": ("concreteness", "abstractness"),
    "external_internal_motivation": ("external_motivation", "internal_motivation"),
}


def upgrade() -> None:
    """
    1. Add new MetricDef records for paired metrics
    2. Migrate participant_metric data: merge single-pole records into paired
    3. Migrate extracted_metric data: create paired records from single-pole
    """
    connection = op.get_bind()

    # Step 1: Add new MetricDef records for paired metrics
    print("Adding paired MetricDef records...")

    insert_metric_def = sa.text("""
        INSERT INTO metric_def (id, code, name, name_ru, min_value, max_value, active)
        VALUES (:id, :code, :name, :name_ru, 1, 10, true)
        ON CONFLICT (code) DO UPDATE SET
            name_ru = EXCLUDED.name_ru,
            name = EXCLUDED.name
    """)

    paired_codes = list(PAIRED_TO_SINGLE.keys())
    for code in paired_codes:
        name_ru = METRIC_DISPLAY_NAMES_RU.get(code, code)
        connection.execute(insert_metric_def, {
            "id": str(uuid.uuid4()),
            "code": code,
            "name": code.replace("_", " ").title(),
            "name_ru": name_ru,
        })

    print(f"Added/updated {len(paired_codes)} paired MetricDef records")

    # Step 2: Migrate participant_metric data
    # For each paired metric, find existing single-pole records and merge them
    print("Migrating participant_metric data...")

    # Get paired metric_def IDs
    get_metric_def_id = sa.text("SELECT id FROM metric_def WHERE code = :code")

    for paired_code, (left_code, right_code) in PAIRED_TO_SINGLE.items():
        # Find participants who have either left or right pole metrics
        find_existing = sa.text("""
            SELECT
                pm.participant_id,
                pm.value,
                pm.confidence,
                pm.last_source_report_id,
                pm.updated_at
            FROM participant_metric pm
            WHERE pm.metric_code IN (:left_code, :right_code)
            ORDER BY pm.participant_id, pm.updated_at DESC
        """)

        rows = connection.execute(find_existing, {
            "left_code": left_code,
            "right_code": right_code,
        }).fetchall()

        if not rows:
            continue

        # Group by participant_id, take the most recent value
        participants = {}
        for row in rows:
            pid = row[0]
            if pid not in participants:
                participants[pid] = {
                    "value": row[1],
                    "confidence": row[2],
                    "last_source_report_id": row[3],
                    "updated_at": row[4],
                }

        # Insert/update paired metric for each participant
        upsert_paired = sa.text("""
            INSERT INTO participant_metric (id, participant_id, metric_code, value, confidence, last_source_report_id, updated_at)
            VALUES (:id, :participant_id, :metric_code, :value, :confidence, :last_source_report_id, :updated_at)
            ON CONFLICT (participant_id, metric_code) DO UPDATE SET
                value = EXCLUDED.value,
                confidence = EXCLUDED.confidence,
                last_source_report_id = EXCLUDED.last_source_report_id,
                updated_at = EXCLUDED.updated_at
        """)

        for pid, data in participants.items():
            connection.execute(upsert_paired, {
                "id": str(uuid.uuid4()),
                "participant_id": pid,
                "metric_code": paired_code,
                "value": data["value"],
                "confidence": data["confidence"],
                "last_source_report_id": data["last_source_report_id"],
                "updated_at": data["updated_at"],
            })

        print(f"  Migrated {len(participants)} records for {paired_code}")

    # Step 3: Migrate extracted_metric data
    print("Migrating extracted_metric data...")

    for paired_code, (left_code, right_code) in PAIRED_TO_SINGLE.items():
        # Get paired metric_def ID
        paired_def_result = connection.execute(get_metric_def_id, {"code": paired_code}).fetchone()
        if not paired_def_result:
            print(f"  WARNING: MetricDef not found for {paired_code}")
            continue
        paired_def_id = paired_def_result[0]

        # Find extracted metrics with single-pole codes
        find_extracted = sa.text("""
            SELECT DISTINCT
                em.report_id,
                em.value,
                em.source,
                em.confidence,
                em.notes,
                md.code
            FROM extracted_metric em
            JOIN metric_def md ON md.id = em.metric_def_id
            WHERE md.code IN (:left_code, :right_code)
        """)

        rows = connection.execute(find_extracted, {
            "left_code": left_code,
            "right_code": right_code,
        }).fetchall()

        if not rows:
            continue

        # Group by report_id, take first value (they should be the same)
        reports = {}
        for row in rows:
            report_id = row[0]
            if report_id not in reports:
                reports[report_id] = {
                    "value": row[1],
                    "source": row[2],
                    "confidence": row[3],
                    "notes": row[4],
                }

        # Insert paired extracted_metric for each report
        insert_extracted = sa.text("""
            INSERT INTO extracted_metric (id, report_id, metric_def_id, value, source, confidence, notes)
            VALUES (:id, :report_id, :metric_def_id, :value, :source, :confidence, :notes)
            ON CONFLICT (report_id, metric_def_id) DO NOTHING
        """)

        for report_id, data in reports.items():
            connection.execute(insert_extracted, {
                "id": str(uuid.uuid4()),
                "report_id": report_id,
                "metric_def_id": paired_def_id,
                "value": data["value"],
                "source": data["source"],
                "confidence": data["confidence"],
                "notes": f"Migrated from single-pole metrics: {left_code}/{right_code}",
            })

        print(f"  Migrated {len(reports)} extracted records for {paired_code}")

    print("Migration completed successfully!")


def downgrade() -> None:
    """
    Remove paired metric records (optional - keeps single-pole records intact).
    This is a non-destructive downgrade.
    """
    connection = op.get_bind()

    paired_codes = list(PAIRED_TO_SINGLE.keys())

    # Remove paired participant_metric records
    delete_participant = sa.text("""
        DELETE FROM participant_metric WHERE metric_code = :code
    """)

    for code in paired_codes:
        connection.execute(delete_participant, {"code": code})

    # Remove paired extracted_metric records
    delete_extracted = sa.text("""
        DELETE FROM extracted_metric em
        USING metric_def md
        WHERE em.metric_def_id = md.id AND md.code = :code
    """)

    for code in paired_codes:
        connection.execute(delete_extracted, {"code": code})

    # Optionally deactivate (not delete) MetricDef records for paired metrics
    deactivate_metric_def = sa.text("""
        UPDATE metric_def SET active = false WHERE code = :code
    """)

    for code in paired_codes:
        connection.execute(deactivate_metric_def, {"code": code})

    print("Downgrade completed - paired metric records removed/deactivated")
