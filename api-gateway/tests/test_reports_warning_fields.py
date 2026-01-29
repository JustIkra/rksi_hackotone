"""
Tests for Report extract_warning and extract_warning_details fields.
"""

import pytest


@pytest.mark.unit
def test_report_schema_has_warning_fields():
    """Verify ReportResponse schema includes extract_warning fields."""
    from app.schemas.report import ReportResponse

    assert "extract_warning" in ReportResponse.model_fields
    assert "extract_warning_details" in ReportResponse.model_fields


@pytest.mark.unit
def test_report_model_has_warning_fields():
    """Verify Report SQLAlchemy model includes extract_warning fields."""
    from app.db.models import Report

    # Check that the columns exist in the model's table
    assert hasattr(Report, "extract_warning")
    assert hasattr(Report, "extract_warning_details")


@pytest.mark.unit
def test_report_schema_warning_fields_nullable():
    """Verify extract_warning fields are optional (nullable)."""
    from app.schemas.report import ReportResponse

    extract_warning_field = ReportResponse.model_fields["extract_warning"]
    extract_warning_details_field = ReportResponse.model_fields["extract_warning_details"]

    # Both fields should allow None
    assert extract_warning_field.is_required() is False
    assert extract_warning_details_field.is_required() is False
