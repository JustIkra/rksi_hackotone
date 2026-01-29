from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_docx_bytes_to_pdf_bytes(docx_data: bytes) -> bytes:
    import shutil
    import subprocess
    import tempfile

    libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_cmd:
        raise RuntimeError(
            "LibreOffice not installed. Install with: "
            "apt-get install libreoffice-writer (Linux) or "
            "brew install --cask libreoffice (macOS)"
        )

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "input.docx"
            docx_path.write_bytes(docx_data)

            result = subprocess.run(
                [
                    libreoffice_cmd,
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", tmpdir,
                    str(docx_path),
                ],
                capture_output=True,
                timeout=120,
                check=False,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"LibreOffice conversion failed: {stderr}")

            pdf_path = Path(tmpdir) / "input.pdf"
            if not pdf_path.exists():
                raise RuntimeError(
                    "LibreOffice conversion produced no output file. "
                    f"stdout: {result.stdout.decode('utf-8', errors='replace')}"
                )

            pdf_data = pdf_path.read_bytes()
            if not pdf_data:
                raise RuntimeError("Conversion produced empty PDF")

            return pdf_data

    except subprocess.TimeoutExpired:
        raise RuntimeError("DOCX to PDF conversion timed out (120s). File may be too large.")
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        logger.exception("DOCX→PDF conversion failed")
        raise RuntimeError(f"DOCX to PDF conversion failed: {e}")
