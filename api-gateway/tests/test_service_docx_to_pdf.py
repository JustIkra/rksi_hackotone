"""
Unit tests for DOCX to PDF conversion.

Tests cover:
- LibreOffice availability check
- Successful conversion
- Timeout handling
- Empty PDF error
- LibreOffice failure error

Markers:
- unit: Unit tests with mocked subprocess
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestConvertDocxToPdf:
    """Test MetricGenerationService.convert_docx_to_pdf method."""

    @pytest.fixture
    def service(self):
        """Create MetricGenerationService instance without DB."""
        from app.services.metric_generation import MetricGenerationService
        return MetricGenerationService(db=MagicMock())

    @pytest.fixture
    def sample_docx_bytes(self):
        """Minimal valid DOCX for testing (empty zip with required structure)."""
        import io
        import zipfile

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            # Minimal DOCX structure
            zf.writestr('[Content_Types].xml', '''<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
</Types>''')
            zf.writestr('_rels/.rels', '''<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>''')
            zf.writestr('word/document.xml', '''<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Test</w:t></w:r></w:p></w:body>
</w:document>''')
        return buffer.getvalue()

    def test_libreoffice_not_installed(self, service):
        """
        Test that RuntimeError is raised when LibreOffice is not found.
        """
        # Arrange
        with patch('shutil.which', return_value=None):
            # Act & Assert
            with pytest.raises(RuntimeError) as exc_info:
                service.convert_docx_to_pdf(b"fake docx")

            assert "LibreOffice not installed" in str(exc_info.value)
            assert "apt-get install" in str(exc_info.value)

    def test_conversion_success(self, service, sample_docx_bytes):
        """
        Test successful DOCX to PDF conversion with mocked LibreOffice.
        """
        # Arrange
        fake_pdf_content = b"%PDF-1.4 fake pdf content"

        def mock_subprocess_run(args, **kwargs):
            # Write fake PDF to output directory
            outdir = args[args.index("--outdir") + 1]
            pdf_path = Path(outdir) / "input.pdf"
            pdf_path.write_bytes(fake_pdf_content)

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = b""
            mock_result.stderr = b""
            return mock_result

        with patch('shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('subprocess.run', side_effect=mock_subprocess_run):
                # Act
                result = service.convert_docx_to_pdf(sample_docx_bytes)

                # Assert
                assert result == fake_pdf_content

    def test_conversion_timeout(self, service, sample_docx_bytes):
        """
        Test that TimeoutExpired is converted to RuntimeError.
        """
        # Arrange
        with patch('shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 120)):
                # Act & Assert
                with pytest.raises(RuntimeError) as exc_info:
                    service.convert_docx_to_pdf(sample_docx_bytes)

                assert "timed out" in str(exc_info.value)
                assert "120" in str(exc_info.value)

    def test_libreoffice_returns_error(self, service, sample_docx_bytes):
        """
        Test handling of non-zero LibreOffice exit code.
        """
        # Arrange
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"Error: cannot open file"
        mock_result.stdout = b""

        with patch('shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('subprocess.run', return_value=mock_result):
                # Act & Assert
                with pytest.raises(RuntimeError) as exc_info:
                    service.convert_docx_to_pdf(sample_docx_bytes)

                assert "conversion failed" in str(exc_info.value).lower()

    def test_empty_pdf_produced(self, service, sample_docx_bytes):
        """
        Test handling when LibreOffice produces empty PDF.
        """
        # Arrange
        def mock_subprocess_run(args, **kwargs):
            outdir = args[args.index("--outdir") + 1]
            pdf_path = Path(outdir) / "input.pdf"
            pdf_path.write_bytes(b"")  # Empty PDF

            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result

        with patch('shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('subprocess.run', side_effect=mock_subprocess_run):
                # Act & Assert
                with pytest.raises(RuntimeError) as exc_info:
                    service.convert_docx_to_pdf(sample_docx_bytes)

                assert "empty PDF" in str(exc_info.value)

    def test_no_pdf_produced(self, service, sample_docx_bytes):
        """
        Test handling when LibreOffice doesn't produce PDF file.
        """
        # Arrange
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"convert input.docx -> input.pdf using filter..."
        mock_result.stderr = b""

        with patch('shutil.which', return_value='/usr/bin/libreoffice'):
            with patch('subprocess.run', return_value=mock_result):
                # PDF file is never created
                # Act & Assert
                with pytest.raises(RuntimeError) as exc_info:
                    service.convert_docx_to_pdf(sample_docx_bytes)

                assert "no output file" in str(exc_info.value).lower()
