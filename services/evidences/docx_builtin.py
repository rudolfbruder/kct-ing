"""The "builtin" Word engine: .docx to PDF with nothing but Python itself.

For machines where no package can be installed (no python-docx, no reportlab, no LibreOffice).
A .docx is a ZIP of XML files; this reads them with the standard library and writes the PDF
with SimplePdf (services/evidences/simple_pdf.py).

    to_pdf(Path("EV-01.docx"), Path("EV-01.pdf"))

Kept: headings, title, paragraphs, bold and italic, bullet and numbered lists, tables (with a
grid, nested tables as text), page breaks, text in text boxes, JPEG and PNG pictures.
Dropped: the exact Word layout (fonts, colours, columns, positions), headers and footers,
pictures in other formats (EMF, WMF, ...; a note "[picture not shown]" is written instead).
Letters outside Western European (Windows-1252) lose their accent, see simple_pdf.py.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree

from services.evidences.exceptions import ConversionError
from services.evidences.simple_pdf import A4, SimplePdf, text_width

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
V = "{urn:schemas-microsoft-com:vml}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

MARGIN = 56.7          # 2 cm
BODY = 10
SIZES = {"title": 20, "h1": 16, "h2": 13.5, "h3": 12, "h4": 11}
CELL = 9


# --- what the document says -----------------------------------------------------------------

@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False


@dataclass
class Para:
    runs: List[Run] = field(default_factory=list)
    style: str = "body"         # body, title, h1 .. h4
    prefix: str = ""            # "• " or "3. " for lists
    indent: int = 0             # list level
    images: List[str] = field(default_factory=list)   # parts inside the .docx, e.g. word/media/image1.png
    page_break: bool = False

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


@dataclass
class TableBlock:
    rows: List[List[str]]


class _Reader:
    def __init__(self, package: zipfile.ZipFile) -> None:
        self.package = package
        names = set(package.namelist())
        if "word/document.xml" not in names:
            raise ConversionError("not a Word document (word/document.xml is missing)")
        self.rels = self._rels("word/_rels/document.xml.rels", names)
        self.styles = self._styles(names)
        self.numbering = self._numbering(names)
        self.counters: Dict[Tuple[str, int], int] = {}

    def _xml(self, name: str):
        return ElementTree.fromstring(self.package.read(name))

    def _rels(self, name: str, names: set) -> Dict[str, str]:
        if name not in names:
            return {}
        found = {}
        for rel in self._xml(name).findall(f"{REL}Relationship"):
            if rel.get("TargetMode") != "External":
                target = rel.get("Target", "")
                found[rel.get("Id")] = target.lstrip("/") if target.startswith("/") else "word/" + target
        return found

    def _styles(self, names: set) -> Dict[str, str]:
        """styleId -> our style (title, h1 .. h4, list or body), following basedOn."""
        if "word/styles.xml" not in names:
            return {}
        raw, based = {}, {}
        for style in self._xml("word/styles.xml").iter(f"{W}style"):
            sid = style.get(f"{W}styleId")
            name = style.find(f"{W}name")
            raw[sid] = (name.get(f"{W}val") if name is not None else sid or "").lower()
            parent = style.find(f"{W}basedOn")
            if parent is not None:
                based[sid] = parent.get(f"{W}val")
        result = {}
        for sid in raw:
            current, seen = sid, set()
            kind = "body"
            while current in raw and current not in seen:
                seen.add(current)
                kind = _style_kind(raw[current], current)
                if kind != "body":
                    break
                current = based.get(current)
            result[sid] = kind
        return result

    def _numbering(self, names: set) -> Dict[str, Dict[int, str]]:
        """numId -> {level: numFmt} ("bullet", "decimal", ...)."""
        if "word/numbering.xml" not in names:
            return {}
        root = self._xml("word/numbering.xml")
        abstract = {}
        for item in root.findall(f"{W}abstractNum"):
            levels = {}
            for lvl in item.findall(f"{W}lvl"):
                fmt = lvl.find(f"{W}numFmt")
                levels[int(lvl.get(f"{W}ilvl", "0"))] = fmt.get(f"{W}val") if fmt is not None else "bullet"
            abstract[item.get(f"{W}abstractNumId")] = levels
        result = {}
        for num in root.findall(f"{W}num"):
            ref = num.find(f"{W}abstractNumId")
            if ref is not None:
                result[num.get(f"{W}numId")] = abstract.get(ref.get(f"{W}val"), {})
        return result

    # --- the body ---------------------------------------------------------------------------

    def blocks(self) -> list:
        body = self._xml("word/document.xml").find(f"{W}body")
        out: list = []
        if body is None:
            return out
        for child in body:
            if child.tag == f"{W}p":
                out.append(self.paragraph(child))
            elif child.tag == f"{W}tbl":
                out.append(TableBlock(self.table_rows(child)))
            elif child.tag == f"{W}sdt":      # content controls wrap ordinary paragraphs and tables
                content = child.find(f"{W}sdtContent")
                for inner in (content if content is not None else []):
                    if inner.tag == f"{W}p":
                        out.append(self.paragraph(inner))
                    elif inner.tag == f"{W}tbl":
                        out.append(TableBlock(self.table_rows(inner)))
        return out

    def paragraph(self, p) -> Para:
        para = Para()
        props = p.find(f"{W}pPr")
        if props is not None:
            style = props.find(f"{W}pStyle")
            kind = self.styles.get(style.get(f"{W}val"), "body") if style is not None else "body"
            if style is not None and kind == "body":
                kind = _style_kind("", style.get(f"{W}val"))
            num = props.find(f"{W}numPr")
            if num is not None or kind == "list":
                para.prefix, para.indent = self._list_prefix(num)
            para.style = kind if kind != "list" else "body"
            if props.find(f"{W}pageBreakBefore") is not None:
                para.page_break = True
        self._collect(p, para)
        return para

    def _list_prefix(self, num) -> Tuple[str, int]:
        if num is None:
            return "• ", 0
        ilvl = num.find(f"{W}ilvl")
        num_id = num.find(f"{W}numId")
        level = int(ilvl.get(f"{W}val", "0")) if ilvl is not None else 0
        nid = num_id.get(f"{W}val", "") if num_id is not None else ""
        if nid == "0":
            return "", 0
        fmt = self.numbering.get(nid, {}).get(level, "bullet")
        if fmt in ("bullet", "none"):
            return ("• " if fmt == "bullet" else ""), level
        key = (nid, level)
        self.counters[key] = self.counters.get(key, 0) + 1
        for (other, deeper) in list(self.counters):   # a new item restarts the deeper levels
            if other == nid and deeper > level:
                del self.counters[(other, deeper)]
        number = self.counters[key]
        label = _letters(number) if "letter" in fmt else _roman(number) if "roman" in fmt else str(number)
        return (label.upper() if "upper" in fmt.lower() else label) + ". ", level

    def _collect(self, element, para: Para) -> None:
        """Runs and pictures inside a paragraph, in order (also inside links and text boxes)."""
        for child in element:
            tag = child.tag
            if tag == f"{MC}Fallback" or tag == f"{W}del" or tag == f"{W}pPr":
                continue                       # Fallback repeats Choice; deleted text is not text
            if tag == f"{W}r":
                self._run(child, para)
            elif tag == f"{W}p":               # a paragraph inside a text box
                inner = self.paragraph(child)
                if inner.runs and para.runs:
                    para.runs.append(Run(" "))
                para.runs.extend(inner.runs)
                para.images.extend(inner.images)
            else:
                self._collect(child, para)

    def _run(self, r, para: Para) -> None:
        props = r.find(f"{W}rPr")
        bold = _on(props, "b")
        italic = _on(props, "i")
        for child in r:
            tag = child.tag
            if tag == f"{W}t":
                para.runs.append(Run(child.text or "", bold, italic))
            elif tag == f"{W}tab":
                para.runs.append(Run("    ", bold, italic))
            elif tag in (f"{W}br", f"{W}cr"):
                if child.get(f"{W}type") == "page":
                    para.runs.append(Run("\f"))
                else:
                    para.runs.append(Run("\n"))
            elif tag == f"{W}noBreakHyphen":
                para.runs.append(Run("-", bold, italic))
            elif tag == f"{W}sym":
                para.runs.append(Run("•"))
            elif tag in (f"{W}drawing", f"{W}pict", f"{W}object", f"{MC}AlternateContent"):
                for blip in child.iter(f"{A}blip"):
                    part = self.rels.get(blip.get(f"{R}embed"))
                    if part:
                        para.images.append(part)
                for image in child.iter(f"{V}imagedata"):
                    part = self.rels.get(image.get(f"{R}id"))
                    if part and tag != f"{W}object":    # an embedded object's icon is not content
                        para.images.append(part)
                for text in child.iter(f"{W}txbxContent"):
                    self._collect(text, para)

    def table_rows(self, tbl) -> List[List[str]]:
        rows = []
        for tr in tbl.findall(f"{W}tr"):
            cells = []
            for tc in tr.findall(f"{W}tc"):
                lines = []
                for child in tc:
                    if child.tag == f"{W}p":
                        para = self.paragraph(child)
                        text = (para.prefix + para.text).strip()
                        if text:
                            lines.append(text)
                    elif child.tag == f"{W}tbl":   # nested table: its rows as text
                        for row in self.table_rows(child):
                            lines.append(" | ".join(c.replace("\n", " ") for c in row))
                cells.append("\n".join(lines))
            if cells:
                rows.append(cells)
        return rows


def _style_kind(name: str, sid: Optional[str]) -> str:
    for value in (name, (sid or "").lower()):
        if value == "title":
            return "title"
        match = re.fullmatch(r"heading ?(\d)", value)
        if match:
            return f"h{min(int(match.group(1)), 4)}"
        if "list" in value and "table" not in value:
            return "list"
    return "body"


def _on(props, name: str) -> bool:
    if props is None:
        return False
    element = props.find(f"{W}{name}")
    return element is not None and element.get(f"{W}val", "true") not in ("0", "false", "off")


def _letters(number: int) -> str:
    out = ""
    while number > 0:
        number, rest = divmod(number - 1, 26)
        out = chr(97 + rest) + out
    return out


def _roman(number: int) -> str:
    out = ""
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
                           (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while number >= value:
            out += letters
            number -= value
    return out


# --- putting it on pages ----------------------------------------------------------------------

class _Layout:
    def __init__(self, pdf: SimplePdf, package: zipfile.ZipFile) -> None:
        self.pdf = pdf
        self.package = package
        self.left = MARGIN
        self.right = pdf.width - MARGIN
        self.top = pdf.height - MARGIN
        self.bottom = MARGIN
        self.y = self.top
        pdf.new_page()

    def page(self) -> None:
        self.pdf.new_page()
        self.y = self.top

    def room(self, height: float) -> None:
        if self.y - height < self.bottom and self.y < self.top:
            self.page()

    def paragraph(self, para: Para) -> None:
        if para.page_break:
            self.page()
        size = SIZES.get(para.style, BODY)
        heading = para.style != "body"
        hang = 14 if para.prefix else 0
        indent = para.indent * 18 + hang
        runs = [Run(r.text, r.bold or heading, r.italic) for r in para.runs]
        if para.prefix:
            runs.insert(0, Run(para.prefix, heading, False))
        lines = _wrap(runs, size, self.right - self.left - indent)
        if heading:
            self.y -= size * 0.6
        if lines == [[]] and not para.images:
            self.y -= size * 0.8      # an empty paragraph: a little space
            return
        leading = size * 1.3
        first = True
        for line in lines:
            if line is None:          # a page break inside the paragraph
                self.page()
                continue
            if not line:
                self.y -= leading
                continue
            self.room(leading)
            self.y -= size
            x = self.left + indent - (hang if first else 0)
            first = False
            for text, font, width in line:
                self.pdf.text(x, self.y, text, font=font, size=size, gray=0.1 if heading else 0.0)
                x += width
            self.y -= leading - size
        for part in para.images:
            self.image(part)
        self.y -= 2 if heading else 4

    def image(self, part: str) -> None:
        try:
            data = self.package.read(part)
        except KeyError:
            return
        image = self.pdf.add_image(data)
        if image is None:
            self.room(BODY * 1.4)
            self.y -= BODY * 1.2
            self.pdf.text(self.left, self.y, f"[picture not shown: {PurePosixPath(part).name}]",
                          font="italic", size=BODY - 1, gray=0.45)
            self.y -= 4
            return
        max_w, max_h = self.right - self.left, (self.top - self.bottom) * 0.9
        scale = min(1.0, max_w / (image.width * 0.75), max_h / (image.height * 0.75))
        w, h = image.width * 0.75 * scale, image.height * 0.75 * scale      # pixels at 96 dpi
        self.room(h + 6)
        self.y -= h + 4
        self.pdf.image(image, self.left, self.y, w, h)
        self.y -= 4

    def table(self, block: TableBlock) -> None:
        rows = block.rows
        columns = max(len(r) for r in rows)
        col_w = (self.right - self.left) / columns
        pad, leading = 3, CELL * 1.25
        self.y -= 4
        for index, row in enumerate(rows):
            row = row + [""] * (columns - len(row))
            wrapped = [_wrap([Run(cell, index == 0)], CELL, col_w - 2 * pad) for cell in row]
            height = max(len(cell) for cell in wrapped) * leading + 2 * pad
            if self.y - height < self.bottom:
                self.page()
            top = self.y
            if index == 0:
                self.pdf.box(self.left, top - height, columns * col_w, height, gray=0.94)
            for col, lines in enumerate(wrapped):
                y = top - pad
                for line in lines:
                    y -= leading
                    x = self.left + col * col_w + pad
                    for text, font, width in line:
                        self.pdf.text(x, y + (leading - CELL) * 0.6, text, font=font, size=CELL)
                        x += width
            self.pdf.line(self.left, top, self.left + columns * col_w, top)
            self.pdf.line(self.left, top - height, self.left + columns * col_w, top - height)
            for col in range(columns + 1):
                x = self.left + col * col_w
                self.pdf.line(x, top, x, top - height)
            self.y = top - height
        self.y -= 8


def _wrap(runs: List[Run], size: float, width: float) -> list:
    """Lines of (text, font, width) pieces that fit the width; '\\n' starts a new line,
    a page break becomes None."""
    lines: list = [[]]
    used = 0.0
    for run in runs:
        if run.text == "\f":
            lines += [None, []]
            used = 0.0
            continue
        font = ("bold" if run.bold else "") + ("italic" if run.italic else "") or "regular"
        for part_index, part in enumerate(run.text.split("\n")):
            if part_index:
                lines.append([])
                used = 0.0
            for word in re.findall(r"\S+\s*|\s+", part):
                w = text_width(word, font, size)
                if used + text_width(word.rstrip(), font, size) > width and used > 0:
                    lines.append([])
                    used = 0.0
                    word = word.lstrip()
                    w = text_width(word, font, size)
                while text_width(word.rstrip(), font, size) > width and len(word) > 1:   # one very long word
                    cut = len(word)
                    while cut > 1 and text_width(word[:cut], font, size) > width - used:
                        cut -= 1
                    lines[-1].append((word[:cut], font, text_width(word[:cut], font, size)))
                    lines.append([])
                    used = 0.0
                    word = word[cut:]
                    w = text_width(word, font, size)
                if word:
                    lines[-1].append((word, font, w))
                    used += w
    return lines


def to_pdf(source: Path, pdf: Path) -> Path:
    """Convert one .docx into pdf, with the standard library only."""
    try:
        package = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise ConversionError(f"{Path(source).name} is not a valid .docx (not a ZIP file)") from exc
    with package:
        try:
            blocks = _Reader(package).blocks()
        except ElementTree.ParseError as exc:
            raise ConversionError(f"{Path(source).name}: the Word XML cannot be read ({exc})") from exc
        writer = SimplePdf(title=Path(source).stem, size=A4)
        layout = _Layout(writer, package)
        for block in blocks:
            if isinstance(block, Para):
                layout.paragraph(block)
            elif block.rows:
                layout.table(block)
        if not blocks:
            writer.text(MARGIN, writer.height - MARGIN - BODY, "(empty document)", font="italic")
        return writer.save(pdf)


def sample_docx(paragraphs: List[str]) -> bytes:
    """A minimal valid .docx with these paragraphs, made with the standard library only.
    Used to check a machine (LibreOffice, engines) without python-docx."""
    from io import BytesIO
    from xml.sax.saxutils import escape

    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>' for text in paragraphs)
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body>{body}</w:body></w:document>",
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as package:
        for name, text in files.items():
            package.writestr(name, text)
    return buffer.getvalue()
