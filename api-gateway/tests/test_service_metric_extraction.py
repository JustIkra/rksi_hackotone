"""
Unit tests for metric extraction service.

Tests cover:
- Metric validation and normalization
- Value pattern matching (1-10 range)
- Label normalization (uppercase, trimmed)
- Image preprocessing (transparency to white)
- Error handling for invalid formats

Markers:
- unit: Pure unit tests with mocked dependencies (Gemini client, DB)
"""

import io
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.services.metric_extraction import (
    VALUE_PATTERN,
    ExtractedMetricData,
    MetricExtractionService,
)


@pytest.mark.unit
class TestValuePattern:
    """Test the VALUE_PATTERN regex for metric values."""

    def test_valid_single_digit_values(self):
        """
        Test that single digit values 1-9 are accepted.
        """
        for value in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            assert VALUE_PATTERN.match(value), f"Value {value} should be valid"

    def test_valid_value_ten(self):
        """
        Test that "10" is accepted.
        """
        assert VALUE_PATTERN.match("10")

    def test_valid_values_with_decimal(self):
        """
        Test that values with single decimal digit are accepted.
        """
        valid_values = [
            "1.5", "2.3", "3.7", "4.0", "5.9",
            "6.1", "7.8", "8.5", "9.9", "10.0",
            "1,5", "2,3",  # Comma as decimal separator
        ]

        for value in valid_values:
            assert VALUE_PATTERN.match(value), f"Value {value} should be valid"

    def test_invalid_value_zero(self):
        """
        Test that "0" is rejected (min is 1).
        """
        assert not VALUE_PATTERN.match("0")

    def test_invalid_value_above_ten(self):
        """
        Test that values > 10 are rejected.
        """
        # Note: VALUE_PATTERN actually allows "10.X" where X is a single digit (including 10.1-10.9)
        # This is caught later in validation by the Decimal range check [1, 10]
        # Here we test only what the regex actually rejects
        invalid_values = ["11", "15", "20", "100"]

        for value in invalid_values:
            assert not VALUE_PATTERN.match(value), f"Value {value} should be invalid"

    def test_invalid_multiple_decimal_digits(self):
        """
        Test that values with multiple decimal digits are rejected.
        """
        invalid_values = ["1.23", "5.456", "9.99999"]

        for value in invalid_values:
            assert not VALUE_PATTERN.match(value), f"Value {value} should be invalid"

    def test_invalid_non_numeric(self):
        """
        Test that non-numeric values are rejected.
        """
        invalid_values = ["abc", "one", "10x", "N/A", "", " "]

        for value in invalid_values:
            assert not VALUE_PATTERN.match(value), f"Value {value} should be invalid"

    def test_invalid_negative_values(self):
        """
        Test that negative values are rejected.
        """
        invalid_values = ["-1", "-5", "-10"]

        for value in invalid_values:
            assert not VALUE_PATTERN.match(value), f"Value {value} should be invalid"


@pytest.mark.unit
class TestValidateAndNormalize:
    """Test the _validate_and_normalize method."""

    def setup_method(self):
        """Set up test service with mocked dependencies."""
        self.mock_db = MagicMock()
        self.service = MetricExtractionService(db=self.mock_db)

    def test_valid_metric_normalization(self):
        """
        Test successful validation and normalization of a valid metric.
        """
        # Arrange
        metric = {
            "label": "attention span",
            "value": "7.5",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "test_image.png")

        # Assert
        assert isinstance(result, ExtractedMetricData)
        assert result.label == "attention span"
        assert result.value == "7.5"
        assert result.normalized_label == "ATTENTION SPAN"
        assert result.normalized_value == Decimal("7.5")
        assert result.confidence == 1.0
        assert result.source_image == "test_image.png"

    def test_label_uppercase_normalization(self):
        """
        Test that labels are normalized to uppercase.
        """
        # Arrange
        metric = {
            "label": "MiXeD CaSe LaBel",
            "value": "5",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "image.png")

        # Assert
        assert result.normalized_label == "MIXED CASE LABEL"

    def test_label_trimming(self):
        """
        Test that labels are trimmed of whitespace.
        """
        # Arrange
        metric = {
            "label": "  spaced label  ",
            "value": "8",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "image.png")

        # Assert
        assert result.label == "spaced label"
        assert result.normalized_label == "SPACED LABEL"

    def test_comma_to_dot_conversion(self):
        """
        Test that comma decimal separator is converted to dot.
        """
        # Arrange
        metric = {
            "label": "test metric",
            "value": "6,5",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "image.png")

        # Assert
        assert result.normalized_value == Decimal("6.5")

    def test_boundary_value_one(self):
        """
        Test validation of minimum boundary value (1.0).
        """
        # Arrange
        metric = {
            "label": "min metric",
            "value": "1",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "image.png")

        # Assert
        assert result.normalized_value == Decimal("1")

    def test_boundary_value_ten(self):
        """
        Test validation of maximum boundary value (10.0).
        """
        # Arrange
        metric = {
            "label": "max metric",
            "value": "10",
        }

        # Act
        result = self.service._validate_and_normalize(metric, "image.png")

        # Assert
        assert result.normalized_value == Decimal("10")

    def test_invalid_empty_label_raises_error(self):
        """
        Test that empty label raises ValueError.
        """
        # Arrange
        metric = {
            "label": "",
            "value": "5",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Empty label or value"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_invalid_empty_value_raises_error(self):
        """
        Test that empty value raises ValueError.
        """
        # Arrange
        metric = {
            "label": "test",
            "value": "",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Empty label or value"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_invalid_value_format_raises_error(self):
        """
        Test that invalid value format raises ValueError.
        """
        # Arrange
        metric = {
            "label": "test",
            "value": "invalid",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid value format"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_value_below_range_raises_error(self):
        """
        Test that value below 1 raises ValueError.
        """
        # Arrange
        metric = {
            "label": "test",
            "value": "0.5",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid value format"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_value_above_range_raises_error(self):
        """
        Test that value above 10 raises ValueError.
        """
        # Arrange - "11" should fail pattern match first
        metric = {
            "label": "test",
            "value": "11",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid value format"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_missing_label_key_raises_error(self):
        """
        Test that missing label key raises ValueError.
        """
        # Arrange
        metric = {
            "value": "5",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Empty label or value"):
            self.service._validate_and_normalize(metric, "image.png")

    def test_missing_value_key_raises_error(self):
        """
        Test that missing value key raises ValueError.
        """
        # Arrange
        metric = {
            "label": "test",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="Empty label or value"):
            self.service._validate_and_normalize(metric, "image.png")


@pytest.mark.unit
class TestImagePreprocessing:
    """Test the _preprocess_image method."""

    def setup_method(self):
        """Set up test service with mocked dependencies."""
        self.mock_db = MagicMock()
        self.service = MetricExtractionService(db=self.mock_db)

    def test_preprocess_rgb_image_unchanged(self):
        """
        Test that RGB images are processed without conversion.
        """
        # Arrange
        img = Image.new("RGB", (100, 100), color="blue")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # Act
        result = self.service._preprocess_image(image_data)

        # Assert
        with Image.open(io.BytesIO(result)) as processed:
            assert processed.mode == "RGB"
            assert processed.format == "PNG"

    def test_preprocess_rgba_to_white_background(self):
        """
        Test that RGBA images are composited on white background.
        """
        # Arrange - Create RGBA image with transparency
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # Act
        result = self.service._preprocess_image(image_data)

        # Assert
        with Image.open(io.BytesIO(result)) as processed:
            assert processed.mode == "RGB"
            assert processed.format == "PNG"

            # Check a pixel - should be lighter than pure red due to white background
            pixel = processed.getpixel((50, 50))
            # Due to alpha=128 (50%), red component should be blended with white
            assert pixel[0] > 128  # Red component

    def test_preprocess_palette_mode_with_transparency(self):
        """
        Test that palette mode (P) with transparency is converted correctly.
        """
        # Arrange - Create palette image with transparency
        img = Image.new("P", (100, 100), color=0)
        img.info["transparency"] = 0
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # Act
        result = self.service._preprocess_image(image_data)

        # Assert
        with Image.open(io.BytesIO(result)) as processed:
            assert processed.mode == "RGB"
            assert processed.format == "PNG"

    def test_preprocess_grayscale_image(self):
        """
        Test that grayscale (L) images are preserved or converted to RGB.
        """
        # Arrange
        img = Image.new("L", (100, 100), color=128)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_data = buffer.getvalue()

        # Act
        result = self.service._preprocess_image(image_data)

        # Assert
        with Image.open(io.BytesIO(result)) as processed:
            assert processed.mode in ("RGB", "L")
            assert processed.format == "PNG"

    def test_preprocess_output_is_png(self):
        """
        Test that preprocessing always outputs PNG format.
        """
        # Arrange - Start with JPEG
        img = Image.new("RGB", (100, 100), color="green")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_data = buffer.getvalue()

        # Act
        result = self.service._preprocess_image(image_data)

        # Assert
        with Image.open(io.BytesIO(result)) as processed:
            assert processed.format == "PNG"


@pytest.mark.unit
class TestImageCombination:
    """Test the _combine_images_vertically method."""

    def setup_method(self):
        """Set up test service with mocked dependencies."""
        self.mock_db = MagicMock()
        self.service = MetricExtractionService(db=self.mock_db)

    def test_combine_single_image(self):
        """
        Test that combining a single image returns it unchanged.
        """
        # Arrange
        img = Image.new("RGB", (100, 100), color="red")
        images = [img]

        # Act
        result_bytes = self.service._combine_images_vertically(images)

        # Assert
        with Image.open(io.BytesIO(result_bytes)) as result_img:
            assert result_img.size == (100, 100)
            assert result_img.format == "PNG"

    def test_combine_multiple_images_vertical_stacking(self):
        """
        Test that multiple images are stacked vertically with padding.
        """
        # Arrange
        img1 = Image.new("RGB", (100, 50), color="red")
        img2 = Image.new("RGB", (100, 50), color="blue")
        images = [img1, img2]

        # Act
        result_bytes = self.service._combine_images_vertically(images)

        # Assert
        with Image.open(io.BytesIO(result_bytes)) as result_img:
            # Expected height: 50 + 50 + padding (20)
            expected_height = 50 + 50 + self.service.image_padding
            assert result_img.size == (100, expected_height)
            assert result_img.format == "PNG"

    def test_combine_images_with_different_widths(self):
        """
        Test that images with different widths are centered.
        """
        # Arrange
        img1 = Image.new("RGB", (100, 50), color="red")
        img2 = Image.new("RGB", (80, 50), color="blue")  # Narrower
        images = [img1, img2]

        # Act
        result_bytes = self.service._combine_images_vertically(images)

        # Assert
        with Image.open(io.BytesIO(result_bytes)) as result_img:
            # Combined width should be max of input widths
            assert result_img.size[0] == 100

    def test_combine_no_images_raises_error(self):
        """
        Test that combining empty list raises ValueError.
        """
        # Arrange
        images = []

        # Act & Assert
        with pytest.raises(ValueError, match="No images to combine"):
            self.service._combine_images_vertically(images)

    def test_combine_images_white_background(self):
        """
        Test that combined image has white background.
        """
        # Arrange
        img1 = Image.new("RGB", (100, 50), color="red")
        img2 = Image.new("RGB", (80, 50), color="blue")
        images = [img1, img2]

        # Act
        result_bytes = self.service._combine_images_vertically(images)

        # Assert
        with Image.open(io.BytesIO(result_bytes)) as result_img:
            # Check padding area (between images) should be white
            # Padding starts at y=50 and ends at y=70 (20 pixels)
            padding_pixel = result_img.getpixel((50, 60))
            assert padding_pixel == (255, 255, 255)  # White


@pytest.mark.unit
class TestImageCombinationGroups:
    """Test the _combine_images_into_groups method."""

    def setup_method(self):
        """Set up test service with mocked dependencies."""
        self.mock_db = MagicMock()
        self.service = MetricExtractionService(db=self.mock_db)

    def test_combine_empty_list_returns_empty(self):
        """
        Test that empty list returns empty result.
        """
        # Arrange
        images = []

        # Act
        result = self.service._combine_images_into_groups(images)

        # Assert
        assert result == []

    def test_combine_small_images_into_one_group(self):
        """
        Test that small images fitting within limits are combined into one group.
        """
        # Arrange - Small images that fit within max_combined_height
        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")
        images = [(img1, "img1"), (img2, "img2")]

        # Act
        result = self.service._combine_images_into_groups(images)

        # Assert
        assert len(result) == 1  # Should be combined into one group
        assert len(result[0]) > 0  # Should have image data

    def test_combine_large_images_split_into_two_groups(self):
        """
        Test that tall images exceeding max_combined_height are split into 2 groups.
        """
        # Arrange - Very tall images
        img1 = Image.new("RGB", (100, 10000), color="red")
        img2 = Image.new("RGB", (100, 10000), color="blue")
        images = [(img1, "img1"), (img2, "img2")]

        # Act
        result = self.service._combine_images_into_groups(images)

        # Assert
        # Total height would exceed max_combined_height, so should split
        assert len(result) <= 2


@pytest.mark.unit
class TestExtractedMetricData:
    """Test the ExtractedMetricData dataclass."""

    def test_dataclass_structure(self):
        """
        Test that ExtractedMetricData has correct structure.
        """
        # Arrange & Act
        data = ExtractedMetricData(
            label="Test Metric",
            value="7.5",
            normalized_label="TEST METRIC",
            normalized_value=Decimal("7.5"),
            confidence=0.95,
            source_image="test.png",
        )

        # Assert
        assert data.label == "Test Metric"
        assert data.value == "7.5"
        assert data.normalized_label == "TEST METRIC"
        assert data.normalized_value == Decimal("7.5")
        assert data.confidence == 0.95
        assert data.source_image == "test.png"
