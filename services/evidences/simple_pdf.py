"""SimplePdf: a very small PDF writer that needs nothing but Python itself.

Used by the "builtin" Word engine (services/evidences/docx_builtin.py) on machines where
no package can be installed (no reportlab, no LibreOffice).

    pdf = SimplePdf(title="EV-01")
    pdf.new_page()
    pdf.text(56, 780, "Hello", font="bold", size=14)
    pdf.line(56, 770, 300, 770)
    image = pdf.add_image(png_bytes)          # None when the format is not supported
    pdf.image(image, 56, 500, 200, 120)
    pdf.save(Path("out.pdf"))

What it can do: A4 pages, the four Helvetica fonts that every PDF reader has (no font
files needed), lines, filled boxes, JPEG and PNG pictures.
Limits: letters are written in the Windows-1252 set (English, Dutch, German, French ...).
Letters outside it lose their accent (č becomes c); other signs become "?".
"""
from __future__ import annotations

import struct
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

A4 = (595.28, 841.89)

FONTS = {"regular": ("F1", "Helvetica"), "bold": ("F2", "Helvetica-Bold"),
         "italic": ("F3", "Helvetica-Oblique"), "bolditalic": ("F4", "Helvetica-BoldOblique")}

# Character widths (1/1000 of the font size) of Helvetica and Helvetica-Bold, characters 32-126,
# from Adobe's standard font metrics. Oblique fonts have the same widths. Other characters use
# a safe, slightly wide value, so lines are never too long.
_REGULAR = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
            556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
            1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
            667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
            333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
            556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
         556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
         975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
         667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
         333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
         611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]
_OTHER = {"regular": 667, "bold": 722}


def to_winansi(text: str) -> bytes:
    """Text as Windows-1252 bytes; accents outside that set are dropped, the rest becomes '?'."""
    out = bytearray()
    for char in text:
        try:
            out += char.encode("cp1252")
            continue
        except UnicodeEncodeError:
            pass
        plain = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
        try:
            out += plain.encode("cp1252") if plain else b"?"
        except UnicodeEncodeError:
            out += b"?"
    return bytes(out)


def text_width(text: str, font: str, size: float) -> float:
    table, other = (_BOLD, _OTHER["bold"]) if font.startswith("bold") else (_REGULAR, _OTHER["regular"])
    total = 0
    for byte in to_winansi(text):
        total += table[byte - 32] if 32 <= byte <= 126 else other
    return total * size / 1000.0


def _escape(data: bytes) -> bytes:
    return data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").replace(b"\r", b"")


@dataclass(frozen=True)
class PdfImage:
    name: str
    width: int      # pixels
    height: int


class SimplePdf:
    def __init__(self, title: str = "", size=A4) -> None:
        self.width, self.height = size
        self.title = title
        self.pages: List[bytearray] = []
        self._images: Dict[str, bytes] = {}      # name -> the image object's dictionary + stream

    # --- drawing ---------------------------------------------------------------------------

    def new_page(self) -> None:
        self.pages.append(bytearray())

    @property
    def _page(self) -> bytearray:
        if not self.pages:
            self.new_page()
        return self.pages[-1]

    def text(self, x: float, y: float, text: str, font: str = "regular", size: float = 10,
             gray: float = 0.0) -> None:
        name = FONTS.get(font, FONTS["regular"])[0]
        self._page.extend(b"BT %.3f g /%s %.2f Tf %.2f %.2f Td (" % (gray, name.encode(), size, x, y)
                          + _escape(to_winansi(text)) + b") Tj ET\n")

    def line(self, x1: float, y1: float, x2: float, y2: float, width: float = 0.5, gray: float = 0.6) -> None:
        self._page.extend(b"%.3f G %.2f w %.2f %.2f m %.2f %.2f l S\n" % (gray, width, x1, y1, x2, y2))

    def box(self, x: float, y: float, w: float, h: float, gray: float = 0.95) -> None:
        self._page.extend(b"%.3f g %.2f %.2f %.2f %.2f re f\n" % (gray, x, y, w, h))

    def image(self, image: PdfImage, x: float, y: float, w: float, h: float) -> None:
        self._page.extend(b"q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q\n" % (w, h, x, y, image.name.encode()))

    # --- pictures ---------------------------------------------------------------------------

    def add_image(self, data: bytes) -> Optional[PdfImage]:
        """Add a JPEG or PNG picture once; None when the format cannot be read."""
        try:
            if data[:3] == b"\xff\xd8\xff":
                found = self._jpeg(data)
            elif data[:8] == b"\x89PNG\r\n\x1a\n":
                found = self._png(data)
            else:
                return None
        except (ValueError, struct.error, zlib.error, IndexError):
            return None
        if found is None:
            return None
        width, height, obj = found
        name = f"Im{len(self._images) + 1}"
        self._images[name] = obj
        return PdfImage(name=name, width=width, height=height)

    @staticmethod
    def _jpeg(data: bytes):
        pos = 2
        while pos < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                pos += 2
                continue
            (length,) = struct.unpack(">H", data[pos + 2:pos + 4])
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack(">HH", data[pos + 5:pos + 9])
                components = data[pos + 9]
                space = {1: b"/DeviceGray", 3: b"/DeviceRGB", 4: b"/DeviceCMYK"}.get(components)
                if not space:
                    return None
                extra = b" /Decode [1 0 1 0 1 0 1 0]" if components == 4 else b""
                head = (b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s "
                        b"/BitsPerComponent 8 /Filter /DCTDecode%s /Length %d >>" % (width, height, space, extra, len(data)))
                return width, height, head + b"\nstream\n" + data + b"\nendstream"
            pos += 2 + length
        return None

    @staticmethod
    def _png(data: bytes):
        pos, idat, palette = 8, bytearray(), b""
        width = height = depth = color = interlace = None
        while pos < len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            kind = data[pos + 4:pos + 8]
            body = data[pos + 8:pos + 8 + length]
            if kind == b"IHDR":
                width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
            elif kind == b"PLTE":
                palette = body
            elif kind == b"IDAT":
                idat += body
            elif kind == b"IEND":
                break
            pos += 12 + length
        if width is None or depth != 8 or interlace:
            return None
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
        if channels is None:
            return None
        if color in (0, 2, 3):   # no transparency: the PNG data can go into the PDF as it is
            colors = 3 if color == 2 else 1
            if color == 3:
                space = b"[/Indexed /DeviceRGB %d <%s>]" % (len(palette) // 3 - 1, palette.hex().encode())
            else:
                space = b"/DeviceRGB" if color == 2 else b"/DeviceGray"
            stream = bytes(idat)
            parms = b"/DecodeParms << /Predictor 15 /Colors %d /BitsPerComponent 8 /Columns %d >>" % (colors, width)
        else:                    # with transparency: drop it (white behind is the page anyway)
            pixels = _unfilter(zlib.decompress(bytes(idat)), width, height, channels)
            keep = channels - 1
            colour = bytearray()
            for start in range(0, len(pixels), channels):
                colour += pixels[start:start + keep]
            stream = zlib.compress(bytes(colour), 6)
            space = b"/DeviceRGB" if keep == 3 else b"/DeviceGray"
            parms = b""
        head = (b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 "
                b"/Filter /FlateDecode %s /Length %d >>" % (width, height, space, parms, len(stream)))
        return width, height, head + b"\nstream\n" + stream + b"\nendstream"

    # --- the file ---------------------------------------------------------------------------

    def save(self, path: Path) -> Path:
        if not self.pages:
            self.new_page()
        objects: List[bytes] = []

        def add(obj: bytes) -> int:
            objects.append(obj)
            return len(objects)

        catalog = add(b"")            # filled in below, once the page tree number is known
        pages_id = add(b"")
        fonts = b" ".join(b"/%s %d 0 R" % (code.encode(), add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % base.encode()))
            for code, base in FONTS.values())
        images = b" ".join(b"/%s %d 0 R" % (name.encode(), add(obj)) for name, obj in self._images.items())
        resources = b"<< /Font << %s >> /XObject << %s >> >>" % (fonts, images)
        kids = []
        for content in self.pages:
            stream = zlib.compress(bytes(content), 6)
            content_id = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
            kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R >>"
                            % (pages_id, self.width, self.height, resources, content_id)))
        objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % k for k in kids), len(kids))
        objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
        info = add(b"<< /Title (" + _escape(to_winansi(self.title)) + b") /Producer (KCT builtin) >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, obj in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1, catalog, info, xref)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(out))
        return path


def _unfilter(raw: bytes, width: int, height: int, channels: int) -> bytes:
    """Undo the PNG row filters (needed only for pictures with transparency)."""
    stride = width * channels
    out = bytearray(stride * height)
    previous = bytearray(stride)
    pos = 0
    for row in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if kind == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif kind == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif kind == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif kind == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        out[row * stride:(row + 1) * stride] = line
        previous = line
    return bytes(out)
