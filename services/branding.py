"""The bank's brand for the PDF report and the demo dashboard.

    from services.branding import brand
    b = brand()
    b.orange, b.navy, b.logo      # logo: Path of the logo file, or None

Colours: ING orange #FF6200 (primary) and ING navy #000066 (secondary). Check them, and the
logo rules, against ING's brand portal before anything leaves the bank.

The logo is a protected trademark and the repository is public, so it is never committed:
put the official file from ING's brand portal at branding/logo.png (or set KCT_BRAND_LOGO).
Without it, the report and dashboard show the brand name as a wordmark in the brand orange.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from services.config import settings


@dataclass(frozen=True)
class Brand:
    name: str
    product: str = "Key Control Testing"
    orange: str = "#FF6200"         # ING orange, primary
    navy: str = "#000066"           # ING navy, secondary
    orange_tint: str = "#FFF1E6"    # light orange for table headers and highlights
    navy_tint: str = "#E6E6F5"
    logo: Optional[Path] = None     # the logo file, when it is there


def brand() -> Brand:
    config = settings()
    logo = Path(config.brand_logo)
    return Brand(name=config.brand_name, logo=logo if logo.is_file() else None)
