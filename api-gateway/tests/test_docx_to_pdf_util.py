import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_convert_docx_bytes_to_pdf_bytes_success(tmp_path: Path):
    from app.services.docx_to_pdf import convert_docx_bytes_to_pdf_bytes

    fake_pdf = b"%PDF-1.4 fake"

    def mock_run(args, **kwargs):
        outdir = args[args.index("--outdir") + 1]
        (Path(outdir) / "input.pdf").write_bytes(fake_pdf)
        result = MagicMock()
        result.returncode = 0
        result.stdout = b""
        result.stderr = b""
        return result

    with patch("shutil.which", return_value="/usr/bin/libreoffice"):
        with patch("subprocess.run", side_effect=mock_run):
            assert convert_docx_bytes_to_pdf_bytes(b"fake-docx") == fake_pdf
