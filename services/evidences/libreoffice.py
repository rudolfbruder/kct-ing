"""LibreOffice in headless mode, shared by the converters. Optional: used only when installed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from services.evidences.exceptions import ConversionError

MAC_APP = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
# Usual install places that are often not on PATH (macOS, Linux, Windows).
KNOWN_PLACES = [
    MAC_APP,
    Path("/usr/lib/libreoffice/program/soffice"),
    Path("/usr/lib64/libreoffice/program/soffice"),
    Path("/opt/libreoffice/program/soffice"),
    Path("/snap/bin/libreoffice"),
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
]


def binary() -> Optional[str]:
    """Path of the soffice program, or None when LibreOffice is not installed."""
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for place in KNOWN_PLACES + sorted(Path("/opt").glob("libreoffice*/program/soffice")):
        if place.is_file():
            return str(place)
    return None


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
