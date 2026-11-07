"""ExcelConverter: an Excel workbook (.xlsx / .xlsm) into what Gemini and Claude can read.

Neither model accepts Excel files, and a PDF alone is a poor substitute for a
wide sheet: tiny text, columns split over pages, and models are not precise at
reading values off a page. Best practice (see README, "Excel evidence") is
text for exact values plus pictures for the look. A workbook becomes:

    <name>.xlsx.md        Every sheet as a Markdown table whose columns are the
                          Excel letters and whose first column is the Excel row
                          number, so the model can cite "F14" like an auditor.
                          What a plain table loses is written next to the value:
                            08:04 {fill: light red} {text: red} {comment: "..."}
                            {merged A1:AF1}  {image 1: <file>}
                          or once at the row number when the whole row has it:
                            14 {row fill: light red}
                          plus hidden rows/columns/sheets and a note when the
                          sheet has conditional formatting.
    <name>.xlsx_images/   The pictures pasted into the sheets, sent to the
                          model as separate images.
    <name>.xlsx.pdf       Only when LibreOffice is installed: a visual copy of
                          every sheet, landscape and scaled to the page width
                          (shows charts and conditional formatting too).

Known gaps without LibreOffice: charts are not rendered, conditional
formatting colors are not evaluated, and formulas show the value Excel saved
last, or the formula itself when the file was never saved by Excel.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from services.evidences import libreoffice
from services.evidences.exceptions import ConversionError

EXCEL_SUFFIXES = (".xlsx", ".xlsm")

# Names for the colors Excel users pick most; anything else is shown as hex.
COLOR_NAMES = {
    "FF0000": "red", "C00000": "dark red", "FFC7CE": "light red", "9C0006": "dark red",
    "FFFF00": "yellow", "FFEB9C": "light yellow", "FFC000": "orange", "F4B084": "light orange",
    "00B050": "green", "92D050": "light green", "C6EFCE": "light green", "006100": "dark green",
    "0070C0": "blue", "00B0F0": "light blue", "BDD7EE": "light blue", "002060": "dark blue",
    "1F4E78": "dark blue", "4472C4": "blue", "7030A0": "purple", "D9D9D9": "grey",
    "BFBFBF": "grey", "808080": "grey", "A6A6A6": "grey", "000000": "black", "FFFFFF": "white",
}


@dataclass
class SheetSummary:
    name: str
    rows: int
    columns: int
    hidden: bool = False
    images: int = 0


@dataclass(frozen=True)
class ExcelConversion:
    source: Path
    text: Path
    images: List[Path]
    sheets: List[SheetSummary]
    pdf: Optional[Path] = None

    @property
    def output(self) -> Path:
        return self.text

    @property
    def engine(self) -> str:
        return "openpyxl + libreoffice" if self.pdf else "openpyxl"

    @property
    def files(self) -> List[Path]:
        """Everything to send to the model."""
        return [self.text, *self.images, *([self.pdf] if self.pdf else [])]

    @property
    def estimated_tokens(self) -> int:
        return self.text.stat().st_size // 4  # about four characters per token


class ExcelConverter:
    """Excel workbook to Markdown text + pictures (+ PDF copy with LibreOffice). See the module docstring.

        converter = ExcelConverter()
        result = converter.convert(Path("EV-03.xlsx"))
        result.text, result.images, result.pdf, result.sheets, result.estimated_tokens
    """

    def __init__(self, with_pdf: Optional[bool] = None) -> None:
        # None: make the PDF copy when LibreOffice is installed; True/False: always/never.
        self.with_pdf = with_pdf

    def convert(self, source: Path, with_pdf: Optional[bool] = None) -> ExcelConversion:
        """Convert one workbook. with_pdf: None = the converter's setting (default: when LibreOffice is installed)."""
        try:
            import openpyxl
        except ImportError as exc:
            raise ConversionError("Missing package openpyxl: pip install openpyxl") from exc

        source = Path(source)
        if source.suffix.lower() not in EXCEL_SUFFIXES:
            raise ConversionError(f"{source.name}: only .xlsx and .xlsm are supported (save .xls as .xlsx first)")
        if not source.is_file():
            raise ConversionError(f"{source} does not exist")

        text_path = source.with_name(source.name + ".md")
        images_dir = source.with_name(source.name + "_images")
        if images_dir.exists():
            shutil.rmtree(images_dir)

        # Two reads: the values Excel last calculated, and the formulas, for cells
        # never calculated (a file written by a program instead of Excel).
        values_book = openpyxl.load_workbook(source, data_only=True)
        formula_book = openpyxl.load_workbook(source, data_only=False)

        total = len(values_book.worksheets)
        out = [
            f"# Workbook: {source.name}",
            "",
            f"{total} sheet(s): " + ", ".join(
                f'"{ws.title}"' + (" (hidden)" if ws.sheet_state != "visible" else "") for ws in values_book.worksheets
            ) + ".",
            "Each table uses the Excel column letters as headers and the Excel row number in the first column,",
            "so a cell is cited as in Excel (for example F14). Formatting that a table cannot show is written",
            "in braces after the value: {fill: ...} background color, {text: ...} font color, {comment: ...},",
            "{merged ...}, {image ...}. {row fill: ...} / {row text: ...} at the row number apply to every",
            "value in that row. Empty rows are left out.",
            "",
        ]
        sheets: List[SheetSummary] = []
        images: List[Path] = []
        for index, ws in enumerate(values_book.worksheets, start=1):
            summary, block, saved = self._sheet(ws, formula_book[ws.title], index, total, images_dir, source)
            sheets.append(summary)
            images.extend(saved)
            out.extend(block)
        text_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

        with_pdf = self.with_pdf if with_pdf is None else with_pdf
        pdf = None
        if with_pdf or (with_pdf is None and libreoffice.binary()):
            pdf = self._libreoffice_pdf(source)
        return ExcelConversion(source=source, text=text_path, images=images, sheets=sheets, pdf=pdf)


    def _sheet(self, ws, formulas, index: int, total: int, images_dir: Path, source: Path):
        from openpyxl.utils import get_column_letter

        hidden_sheet = ws.sheet_state != "visible"
        heading = f'## Sheet {index} of {total}: "{ws.title}"' + (" (HIDDEN sheet)" if hidden_sheet else "")

        # Images first: their anchor cells must be inside the table.
        marks: Dict[Tuple[int, int], List[str]] = {}
        saved: List[Path] = []
        for number, image in enumerate(getattr(ws, "_images", []), start=1):
            row, column = self._anchor(image)
            suffix = "." + (getattr(image, "format", None) or "png").lower()
            images_dir.mkdir(parents=True, exist_ok=True)
            path = images_dir / f"sheet{index}_image{number}{suffix}"
            path.write_bytes(image._data())
            saved.append(path)
            marks.setdefault((row, column), []).append(f"{{image {number}: attached as {path.name}}}")

        merged_extra: Dict[Tuple[int, int], str] = {}
        covered = set()
        for merged in ws.merged_cells.ranges:
            merged_extra[(merged.min_row, merged.min_col)] = f"{{merged {merged.coord}}}"
            for row in range(merged.min_row, merged.max_row + 1):
                for column in range(merged.min_col, merged.max_col + 1):
                    if (row, column) != (merged.min_row, merged.min_col):
                        covered.add((row, column))

        last_row, last_col = self._used_range(ws, marks)
        if last_row == 0:
            return SheetSummary(ws.title, 0, 0, hidden_sheet), [heading, "", "(empty sheet)", ""], saved

        hidden_cols = {c for c in range(1, last_col + 1)
                       if ws.column_dimensions[get_column_letter(c)].hidden}
        hidden_rows = {r for r, dim in ws.row_dimensions.items() if dim.hidden and r <= last_row}

        block = [heading, "", f"Rows 1-{last_row}, columns A-{get_column_letter(last_col)} "
                              f"({last_row} rows x {last_col} columns).", ""]
        header = ["Row"] + [get_column_letter(c) + (" (hidden)" if c in hidden_cols else "")
                            for c in range(1, last_col + 1)]
        block.append("| " + " | ".join(header) + " |")
        block.append("|" + "---|" * len(header))

        for row in ws.iter_rows(min_row=1, max_row=last_row, max_col=last_col):
            # A color shared by every filled cell of the row is written once, at the row number.
            row_fill = self._shared(row, covered, lambda c: self._fill_color(c))
            row_font = self._shared(row, covered, lambda c: self._font_color(c) if c.value is not None else None)
            cells = []
            for cell in row:
                key = (cell.row, cell.column)
                if key in covered:
                    cells.append("")
                    continue
                parts = [self._value(cell, formulas)]
                fill = self._fill_color(cell)
                if fill and fill != row_fill:
                    parts.append(f"{{fill: {fill}}}")
                font = self._font_color(cell)
                if font and cell.value is not None and font != row_font:
                    parts.append(f"{{text: {font}}}")
                if cell.comment is not None:
                    text = " ".join(cell.comment.text.split())
                    author = f" ({cell.comment.author})" if cell.comment.author else ""
                    parts.append(f'{{comment: "{text}"{author}}}')
                if key in merged_extra:
                    parts.append(merged_extra[key])
                parts.extend(marks.get(key, []))
                cells.append(self._md(" ".join(p for p in parts if p)))
            if not any(cells):
                continue
            number = f"{row[0].row}" + (" (hidden)" if row[0].row in hidden_rows else "")
            if row_fill:
                number += f" {{row fill: {row_fill}}}"
            if row_font:
                number += f" {{row text: {row_font}}}"
            block.append("| " + " | ".join([number] + cells) + " |")

        notes = []
        if ws.conditional_formatting:
            ranges = ", ".join(str(cf.sqref) for cf in ws.conditional_formatting)
            notes.append(f"Conditional formatting on {ranges}: its colors depend on Excel rules and are not shown above.")
        if notes:
            block += ["", *notes]
        block.append("")
        return SheetSummary(ws.title, last_row, last_col, hidden_sheet, len(saved)), block, saved


    def _shared(self, row, covered, color_of) -> Optional[str]:
        """The color every non-empty cell of the row has, when there are at least three such cells."""
        colors = [color_of(c) for c in row
                  if (c.row, c.column) not in covered and c.value is not None and str(c.value).strip()]
        if len(colors) >= 3 and colors[0] and all(color == colors[0] for color in colors):
            return colors[0]
        return None


    def _used_range(self, ws, marks) -> Tuple[int, int]:
        """Last row and column holding a value, a fill or an image. ws.max_row also counts empty formatted cells."""
        last_row = last_col = 0
        for row in ws.iter_rows():
            for cell in row:
                has_value = cell.value is not None and str(cell.value).strip() != ""
                if has_value or (cell.comment is not None) or self._fill_color(cell):
                    last_row, last_col = max(last_row, cell.row), max(last_col, cell.column)
        for row, column in marks:
            last_row, last_col = max(last_row, row), max(last_col, column)
        return last_row, last_col


    def _value(self, cell, formulas) -> str:
        value = cell.value
        if value is None:
            formula = formulas[cell.coordinate].value
            if isinstance(formula, str) and formula.startswith("="):
                return f"{formula} {{formula, not calculated}}"
            return ""
        if isinstance(value, datetime):
            if value.time() == time(0, 0):
                return value.date().isoformat()  # a date stored as date-time
            return value.isoformat(sep=" ", timespec="minutes" if value.second == 0 else "seconds")
        if isinstance(value, (date, time)):
            return value.isoformat()
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, float):
            if "%" in (cell.number_format or ""):
                return f"{value * 100:g}%"
            return f"{value:g}" if abs(value) < 1e15 else str(value)
        return str(value)


    def _md(self, text: str) -> str:
        """Make a value safe inside a Markdown table cell."""
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


    def _fill_color(self, cell) -> Optional[str]:
        fill = cell.fill
        if fill is None or fill.fill_type in (None, "none"):
            return None
        return self._color_name(fill.fgColor, skip=("FFFFFF",))


    def _font_color(self, cell) -> Optional[str]:
        if cell.font is None or cell.font.color is None:
            return None
        return self._color_name(cell.font.color, skip=("000000",))


    def _color_name(self, color, skip=()) -> Optional[str]:
        if color is None:
            return None
        if color.type == "rgb" and isinstance(color.rgb, str):
            rgb = color.rgb[-6:].upper()
            return None if rgb in skip else COLOR_NAMES.get(rgb, f"#{rgb}")
        if color.type == "theme":
            # Theme colors depend on the workbook's theme; the index is the best we can say.
            if color.theme in (0, 1) and not color.tint:
                return None  # theme background/text: plain white/black
            return f"theme color {color.theme}" + (f" tint {color.tint:+.1f}" if color.tint else "")
        if color.type == "indexed":
            from openpyxl.styles.colors import COLOR_INDEX

            if color.indexed in (64, 65) or not 0 <= color.indexed < len(COLOR_INDEX):
                return None  # system foreground/background
            rgb = COLOR_INDEX[color.indexed][-6:].upper()
            return None if rgb in skip else COLOR_NAMES.get(rgb, f"#{rgb}")
        return None


    def _anchor(self, image) -> Tuple[int, int]:
        marker = getattr(image.anchor, "_from", None)
        if marker is None:
            return 1, 1
        return marker.row + 1, marker.col + 1


    def _libreoffice_pdf(self, source: Path) -> Path:
        """Visual copy: every sheet landscape, fitted to the page width, via LibreOffice."""
        import openpyxl

        if not libreoffice.binary():
            raise ConversionError("LibreOffice is not installed")
        with tempfile.TemporaryDirectory() as work:
            # Print settings on a copy, so the evidence file itself is never changed.
            copy = Path(work) / f"{source.stem}.xlsx"
            book = openpyxl.load_workbook(source)
            for ws in book.worksheets:
                ws.page_setup.orientation = "landscape"
                ws.page_setup.fitToWidth = 1
                ws.page_setup.fitToHeight = 0
                ws.sheet_properties.pageSetUpPr.fitToPage = True
            book.save(copy)
            return libreoffice.to_pdf(copy, source.with_name(source.name + ".pdf"))
