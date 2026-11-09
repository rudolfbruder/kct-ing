"""Fake screenshots for the evidence factories, drawn with Pillow."""
from __future__ import annotations

from io import BytesIO

RESETS = [
    ("SD-104233", "2026-01-08 09:12", "2026-01-08 09:15", "AGT-0193", "AGT-0193", "Callback + employee ID"),
    ("SD-104871", "2026-02-02 14:40", "2026-02-02 14:43", "AGT-0207", "AGT-0207", "Callback + manager confirmation"),
    ("SD-105112", "2026-02-19 08:05", "2026-02-19 08:04", "AGT-0193", "AGT-0211", "Employee ID only"),
]


def audit_log_screenshot() -> BytesIO:
    """A fake 'audit log' screenshot, drawn with Pillow."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (900, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 899, 34], fill=(32, 64, 128))
    draw.text((12, 10), "ADX Audit Log - password reset events (SAMPLE)", fill="white")
    y = 50
    for ticket, verified, reset, verifier, executor, _ in RESETS:
        draw.text((12, y), f"{reset}  RESET_PASSWORD  ticket={ticket}  executed_by={executor}  verified_by={verifier}",
                  fill="black")
        y += 30
    draw.text((12, y + 20), "Exported 2026-03-31 by IAM Operations", fill=(110, 110, 110))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def ticket_screenshot(ticket: str, status: str = "Resolved", agent: str = "AGT-0193") -> BytesIO:
    """A fake ServiceNow ticket screenshot, drawn with Pillow."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (720, 220), (245, 246, 248))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 719, 32], fill=(41, 54, 66))
    draw.text((12, 10), f"ServiceNow - Incident {ticket} (SAMPLE)", fill="white")
    fields = [("Number", ticket), ("Category", "Password reset"), ("State", status),
              ("Assigned to", agent), ("Identity verified", "Yes - callback")]
    for row, (label, value) in enumerate(fields):
        y = 50 + row * 30
        draw.text((16, y), label, fill=(90, 90, 90))
        draw.rectangle([180, y - 4, 700, y + 18], outline=(200, 200, 200), fill="white")
        draw.text((188, y), value, fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
