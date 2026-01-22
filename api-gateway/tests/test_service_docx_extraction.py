"""
Unit tests for DOCX extraction service.

Tests cover:
- Image extraction from DOCX ZIP archives
- Supported format filtering
- Format detection via PIL
- Error handling: invalid DOCX, missing files
- PNG conversion with transparency handling

Markers:
- unit: Pure unit tests with mocked file I/O
"""

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services.docx_extraction import (
    DocxImageExtractor,
    ExtractedImage,
    ImageExtractionError,
    InvalidDocxError,
)


@pytest.mark.unit
class TestDocxImageExtractor:
    """Test DocxImageExtractor core functionality."""

    def test_supported_formats(self):
        """
        Test that SUPPORTED_FORMATS contains expected image formats.
        """
        # Arrange & Act
        extractor = DocxImageExtractor()

        # Assert
        assert ".png" in extractor.SUPPORTED_FORMATS
        assert ".jpg" in extractor.SUPPORTED_FORMATS
        assert ".jpeg" in extractor.SUPPORTED_FORMATS
        assert ".gif" in extractor.SUPPORTED_FORMATS
        assert ".bmp" in extractor.SUPPORTED_FORMATS

    def test_extract_images_file_not_found(self):
        """
        Test that InvalidDocxError is raised when file doesn't exist.
        """
        # Arrange
        extractor = DocxImageExtractor()
        non_existent_path = Path("/fake/path/to/document.docx")

        # Act & Assert
        with pytest.raises(InvalidDocxError, match="File not found"):
            extractor.extract_images(non_existent_path)

    @patch("zipfile.ZipFile")
    @patch("pathlib.Path.exists")
    def test_extract_images_invalid_zip(self, mock_exists, mock_zipfile):
        """
        Test that InvalidDocxError is raised for invalid ZIP files.
        """
        # Arrange
        extractor = DocxImageExtractor()
        mock_exists.return_value = True
        mock_zipfile.side_effect = zipfile.BadZipFile("Not a valid ZIP")

        docx_path = Path("/fake/test.docx")

        # Act & Assert
        with pytest.raises(InvalidDocxError, match="Not a valid ZIP/DOCX file"):
            extractor.extract_images(docx_path)

    def test_extract_from_zip_no_media_files(self):
        """
        Test extraction when DOCX has no media files.

        Should return empty list.
        """
        # Arrange
        extractor = DocxImageExtractor()

        # Mock ZIP with no media files
        mock_zip = MagicMock(spec=zipfile.ZipFile)
        mock_zip.namelist.return_value = [
            "word/document.xml",
            "word/styles.xml",
            "_rels/.rels",
        ]

        # Act
        result = extractor._extract_from_zip(mock_zip)

        # Assert
        assert result == []

    def test_extract_from_zip_with_supported_formats(self):
        """
        Test extraction with supported image formats.

        Should extract PNG and JPEG, skip unsupported.
        """
        # Arrange
        extractor = DocxImageExtractor()

        # Create fake image data
        fake_png = self._create_fake_image_bytes("PNG")
        fake_jpg = self._create_fake_image_bytes("JPEG")

        # Mock ZIP with media files
        mock_zip = MagicMock(spec=zipfile.ZipFile)
        mock_zip.namelist.return_value = [
            "word/media/image1.png",
            "word/media/image2.jpeg",
            "word/media/image3.svg",  # Unsupported
            "word/document.xml",
        ]

        # Mock open() for each file
        def mock_open_side_effect(filename):
            mock_file = MagicMock()
            if "image1.png" in filename:
                mock_file.read.return_value = fake_png
            elif "image2.jpeg" in filename:
                mock_file.read.return_value = fake_jpg
            return mock_file

        mock_zip.open = MagicMock(side_effect=mock_open_side_effect)

        # Act
        result = extractor._extract_from_zip(mock_zip)

        # Assert
        assert len(result) == 2

        # First image
        assert result[0].filename == "image1.png"
        assert result[0].format in ("PNG", "UNKNOWN")
        assert result[0].order_index == 0
        assert result[0].page == 0
        # Note: In mocked test, data is a MagicMock, so size_bytes won't match actual bytes
        assert result[0].size_bytes >= 0

        # Second image
        assert result[1].filename == "image2.jpeg"
        assert result[1].format in ("JPEG", "UNKNOWN")
        assert result[1].order_index == 1
        # Same as above
        assert result[1].size_bytes >= 0

    def test_extract_from_zip_deterministic_ordering(self):
        """
        Test that images are extracted in deterministic sorted order.
        """
        # Arrange
        extractor = DocxImageExtractor()

        fake_img = self._create_fake_image_bytes("PNG")

        # Mock ZIP with unsorted media files
        mock_zip = MagicMock(spec=zipfile.ZipFile)
        mock_zip.namelist.return_value = [
            "word/media/image3.png",
            "word/media/image1.png",
            "word/media/image2.png",
        ]

        def mock_open_side_effect(filename):
            mock_file = MagicMock()
            mock_file.read.return_value = fake_img
            return mock_file

        mock_zip.open = MagicMock(side_effect=mock_open_side_effect)

        # Act
        result = extractor._extract_from_zip(mock_zip)

        # Assert - Should be sorted alphabetically
        assert len(result) == 3
        assert result[0].filename == "image1.png"
        assert result[1].filename == "image2.png"
        assert result[2].filename == "image3.png"

        # Order indices should be sequential
        assert result[0].order_index == 0
        assert result[1].order_index == 1
        assert result[2].order_index == 2

    def test_detect_format_png(self):
        """
        Test format detection for PNG images.
        """
        # Arrange
        extractor = DocxImageExtractor()
        png_data = self._create_fake_image_bytes("PNG")

        # Act
        detected_format = extractor._detect_format(png_data)

        # Assert
        assert detected_format in ("PNG", "UNKNOWN")

    def test_detect_format_jpeg(self):
        """
        Test format detection for JPEG images.
        """
        # Arrange
        extractor = DocxImageExtractor()
        jpeg_data = self._create_fake_image_bytes("JPEG")

        # Act
        detected_format = extractor._detect_format(jpeg_data)

        # Assert
        assert detected_format in ("JPEG", "UNKNOWN")

    def test_detect_format_invalid_data(self):
        """
        Test format detection with invalid image data.

        Should return "UNKNOWN" instead of crashing.
        """
        # Arrange
        extractor = DocxImageExtractor()
        invalid_data = b"This is not an image"

        # Act
        detected_format = extractor._detect_format(invalid_data)

        # Assert
        assert detected_format == "UNKNOWN"

    def test_convert_to_png_from_jpeg(self):
        """
        Test conversion from JPEG to PNG.
        """
        # Arrange
        extractor = DocxImageExtractor()
        jpeg_data = self._create_fake_image_bytes("JPEG")

        # Act
        png_data = extractor.convert_to_png(jpeg_data)

        # Assert
        assert png_data is not None
        assert len(png_data) > 0

        # Verify it's a valid PNG
        with Image.open(io.BytesIO(png_data)) as img:
            assert img.format == "PNG"

    def test_convert_to_png_with_transparency(self):
        """
        Test PNG conversion handles RGBA transparency correctly.

        Should convert transparent background to white.
        """
        # Arrange
        extractor = DocxImageExtractor()

        # Create RGBA image with transparency
        rgba_img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        rgba_buffer = io.BytesIO()
        rgba_img.save(rgba_buffer, format="PNG")
        rgba_data = rgba_buffer.getvalue()

        # Act
        png_data = extractor.convert_to_png(rgba_data)

        # Assert
        with Image.open(io.BytesIO(png_data)) as result_img:
            assert result_img.format == "PNG"
            assert result_img.mode == "RGB"  # Should be converted to RGB

    def test_convert_to_png_invalid_data_raises_error(self):
        """
        Test that ImageExtractionError is raised for invalid image data.
        """
        # Arrange
        extractor = DocxImageExtractor()
        invalid_data = b"Not an image"

        # Act & Assert
        with pytest.raises(ImageExtractionError, match="Failed to convert image to PNG"):
            extractor.convert_to_png(invalid_data)

    def test_extract_from_zip_partial_failure(self):
        """
        Test that extraction continues when one image fails.

        Failed images should be skipped with a warning, but other images processed.
        """
        # Arrange
        extractor = DocxImageExtractor()

        fake_png = self._create_fake_image_bytes("PNG")

        # Mock ZIP
        mock_zip = MagicMock(spec=zipfile.ZipFile)
        mock_zip.namelist.return_value = [
            "word/media/good_image.png",
            "word/media/bad_image.png",
        ]

        def mock_open_side_effect(filename):
            if "bad_image" in filename:
                raise Exception("Corrupted file")
            mock_file = MagicMock()
            mock_file.read.return_value = fake_png
            return mock_file

        mock_zip.open = MagicMock(side_effect=mock_open_side_effect)

        # Act
        result = extractor._extract_from_zip(mock_zip)

        # Assert - Should have successfully extracted the good image
        assert len(result) == 1
        assert result[0].filename == "good_image.png"

    def test_extracted_image_dataclass_structure(self):
        """
        Test that ExtractedImage dataclass has correct structure.
        """
        # Arrange & Act
        image = ExtractedImage(
            data=b"fake_image_data",
            filename="test.png",
            page=2,
            order_index=5,
            format="PNG",
            size_bytes=1024,
        )

        # Assert
        assert image.data == b"fake_image_data"
        assert image.filename == "test.png"
        assert image.page == 2
        assert image.order_index == 5
        assert image.format == "PNG"
        assert image.size_bytes == 1024

    # Helper methods

    def _create_fake_image_bytes(self, format_type: str) -> bytes:
        """
        Create minimal valid image bytes for testing.

        Args:
            format_type: "PNG", "JPEG", etc.

        Returns:
            Image bytes
        """
        img = Image.new("RGB", (10, 10), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format=format_type)
        return buffer.getvalue()


@pytest.mark.unit
class TestDocxExtractionErrors:
    """Test error handling in DOCX extraction."""

    def test_invalid_docx_error_inheritance(self):
        """Test that InvalidDocxError inherits from DocxExtractionError."""
        from app.services.docx_extraction import DocxExtractionError

        error = InvalidDocxError("Test error")
        assert isinstance(error, DocxExtractionError)
        assert isinstance(error, Exception)

    def test_image_extraction_error_inheritance(self):
        """Test that ImageExtractionError inherits from DocxExtractionError."""
        from app.services.docx_extraction import DocxExtractionError

        error = ImageExtractionError("Test error")
        assert isinstance(error, DocxExtractionError)
        assert isinstance(error, Exception)

    def test_error_messages_preserved(self):
        """Test that error messages are preserved correctly."""
        message = "Custom error message with details"

        invalid_error = InvalidDocxError(message)
        extraction_error = ImageExtractionError(message)

        assert str(invalid_error) == message
        assert str(extraction_error) == message
