"""LibreOffice in headless mode, shared by the converters. Optional: used only when installed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from services.evidences.exceptions import ConversionError

MAC_APP = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def binary() -> Optional[str]:
    """Path of the soffice program, or None when LibreOffice is not installed."""
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    return str(MAC_APP) if MAC_APP.is_file() else None


def to_pdf(source: Path, pdf: Path, timeout: int = 300) -> Path:
    """Convert any document LibreOffice opens (.docx, .xlsx, ...) to pdf."""
    program = binary()
    if not program:
        raise ConversionError("LibreOffice is not installed")
    with tempfile.TemporaryDirectory() as out_dir:
        result = subprocess.run(
            [program, "--headless", "--convert-to", "pdf", "--outdir", out_dir, str(source)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        produced = Path(out_dir) / f"{Path(source).stem}.pdf"
        if result.returncode != 0 or not produced.is_file():
            raise ConversionError(f"LibreOffice failed: {result.stderr.strip() or result.stdout.strip()}")
        pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), pdf)
    return pdf
