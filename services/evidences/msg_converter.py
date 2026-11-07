"""MsgConverter: an Outlook email (.msg) into what Gemini and Claude can read.

Neither model accepts .msg (Outlook's binary format). An email becomes:

    <name>.msg.md                The email as text: From, To, Cc, date, subject,
                                 the body (from the HTML version when there is
                                 one, keeping lists, tables, red text, links as
                                 "text (url)" and where inline images sit), each
                                 earlier email of the thread marked as its own
                                 section ("### Earlier email 2 of 5"), and a list
                                 of attachments saying what each became.
    <name>.msg_attachments/      Every attachment, saved and converted with the
                                 other converters:
                                   .docx        -> PDF (DocxConverter)
                                   .xlsx/.xlsm  -> text + pictures (ExcelConverter)
                                   .msg / attached email -> converted the same way (nested)
                                   .pdf, images, .txt, .csv -> sent as they are
                                   anything else -> listed, not sent (not readable by the models)

A broken attachment never fails the whole email; it is listed with the reason.
Reads .msg with extract-msg (GPL-3.0 licensed).
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from services.ai.attachments import MIME_TYPES
from services.evidences.docx_converter import DocxConverter
from services.evidences.excel_converter import EXCEL_SUFFIXES, ExcelConverter
from services.evidences.exceptions import ConversionError

MAX_DEPTH = 3  # emails attached to emails attached to emails...


@dataclass
class AttachmentResult:
    name: str
    kind: str                    # word, excel, email, pdf, image, text, other
    size: int
    outputs: List[Path] = field(default_factory=list)   # files the AI gets for it
    note: str = ""


@dataclass(frozen=True)
class MsgConversion:
    source: Path
    text: Path
    subject: str
    attachments: List[AttachmentResult]
    files: List[Path]            # everything to send to the model: the .md and every attachment output

    @property
    def output(self) -> Path:
        return self.text

    @property
    def engine(self) -> str:
        return "extract-msg"

    @property
    def estimated_tokens(self) -> int:
        return self.text.stat().st_size // 4


class MsgConverter:
    def __init__(self, docx: Optional[DocxConverter] = None, excel: Optional[ExcelConverter] = None) -> None:
        self.docx = docx or DocxConverter()
        self.excel = excel or ExcelConverter()

    def convert(self, source: Path) -> MsgConversion:
        try:
            import extract_msg
        except ImportError as exc:
            raise ConversionError("Missing package extract-msg: pip install extract-msg") from exc

        source = Path(source)
        if source.suffix.lower() != ".msg":
            raise ConversionError(f"{source.name}: only .msg is supported")
        if not source.is_file():
            raise ConversionError(f"{source} does not exist")
        try:
            message = extract_msg.openMsg(str(source))
        except Exception as exc:  # extract-msg raises many kinds for damaged files
            raise ConversionError(f"{source.name}: cannot read the email: {exc}") from exc
        try:
            return self._convert_message(message, source, source.with_name(source.name + ".md"),
                                         source.with_name(source.name + "_attachments"), depth=0)
        finally:
            message.close()

    # --- one message ------------------------------------------------------------------

    def _convert_message(self, message, source: Path, text_path: Path, folder: Path, depth: int) -> MsgConversion:
        if folder.exists():
            shutil.rmtree(folder)
        results = [self._attachment(message, attachment, number, folder, depth)
                   for number, attachment in enumerate(message.attachments, start=1)]
        inline = {a.contentId: r.name for a, r in zip(message.attachments, results)
                  if getattr(a, "contentId", None)}

        body, earlier = self._split_thread(self._body(message, inline))
        lines = [f"# Email: {message.subject or '(no subject)'}", "", "| Field | Value |", "|---|---|"]
        for label, value in (
            ("From", message.sender),
            ("To", message.to),
            ("Cc", message.cc),
            ("Date", self._date(message.date)),
            ("Subject", message.subject),
            ("Attachments", str(len(results))),
            ("Earlier emails quoted in the thread", str(earlier) if earlier else ""),
        ):
            if value:
                lines.append(f"| {label} | {self._cell(str(value))} |")
        lines += ["", "## Body", "", body.strip() or "(empty)", ""]

        if results:
            lines += ["## Attachments", ""]
            for number, result in enumerate(results, start=1):
                lines.append(f"{number}. {self._describe(result, text_path.parent)}")
            lines.append("")
        text_path.write_text("\n".join(lines), encoding="utf-8")

        files = [text_path] + [output for result in results for output in result.outputs]
        return MsgConversion(source=source, text=text_path, subject=message.subject or "",
                             attachments=results, files=files)

    # --- attachments -----------------------------------------------------------------

    def _attachment(self, message, attachment, number: int, folder: Path, depth: int) -> AttachmentResult:
        data = attachment.data
        is_email = data is not None and not isinstance(data, (bytes, bytearray))
        if is_email:
            subject = getattr(data, "subject", None) or "attached email"
            result = AttachmentResult(name=f'email "{subject}"', kind="email", size=0)
            if depth + 1 > MAX_DEPTH:
                result.note = f"not converted: emails nested deeper than {MAX_DEPTH} levels"
                return result
            stem = f"{number:02d}_{self._safe(subject)[:60]}"
            folder.mkdir(parents=True, exist_ok=True)
            nested = self._convert_message(data, folder / f"{stem}.msg", folder / f"{stem}.msg.md",
                                           folder / f"{stem}.msg_attachments", depth + 1)
            result.outputs = nested.files
            return result

        name = (getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", None)
                or f"attachment_{number}")
        data = bytes(data or b"")
        result = AttachmentResult(name=name, kind="other", size=len(data))
        if getattr(attachment, "contentId", None):
            result.note = "shown inside the body"
        folder.mkdir(parents=True, exist_ok=True)
        path = self._unique(folder / self._safe(name))
        path.write_bytes(data)

        suffix = path.suffix.lower()
        try:
            if suffix == ".docx":
                result.kind = "word"
                result.outputs = [self.docx.convert(path).pdf]
            elif suffix in EXCEL_SUFFIXES:
                result.kind = "excel"
                result.outputs = self.excel.convert(path).files
            elif suffix == ".msg":
                result.kind = "email"
                if depth + 1 > MAX_DEPTH:
                    result.note = f"not converted: emails nested deeper than {MAX_DEPTH} levels"
                else:
                    import extract_msg

                    inner = extract_msg.openMsg(str(path))
                    try:
                        result.outputs = self._convert_message(
                            inner, path, path.with_name(path.name + ".md"),
                            path.with_name(path.name + "_attachments"), depth + 1).files
                    finally:
                        inner.close()
            elif suffix in MIME_TYPES:
                mime = MIME_TYPES[suffix]
                result.kind = "pdf" if suffix == ".pdf" else mime.split("/")[0]
                result.outputs = [path]
            else:
                result.note = (result.note + "; " if result.note else "") + \
                    f"not sent to the AI: {suffix or 'no extension'} is not a readable format"
        except Exception as exc:  # one bad attachment must not lose the rest of the email
            result.note = (result.note + "; " if result.note else "") + f"conversion failed: {exc}"
            result.outputs = []
        return result

    def _describe(self, result: AttachmentResult, base: Path) -> str:
        labels = {"word": "Word", "excel": "Excel", "email": "attached email", "pdf": "PDF",
                  "image": "image", "text": "text", "other": "file"}
        size = f", {result.size / 1024:.1f} KB" if result.size else ""
        parts = [f"`{result.name}` ({labels.get(result.kind, result.kind)}{size})"]
        if result.outputs:
            shown = [str(p.relative_to(base)) for p in result.outputs[:3]]
            more = f" and {len(result.outputs) - 3} more file(s)" if len(result.outputs) > 3 else ""
            parts.append("attached as " + ", ".join(f"`{s}`" for s in shown) + more)
        if result.note:
            parts.append(result.note)
        return ": ".join(parts[:2]) + ("; " + parts[2] if len(parts) > 2 else "")

    # --- body ------------------------------------------------------------------------

    def _body(self, message, inline: dict) -> str:
        """The body as text. HTML is preferred: it keeps lists, tables, colors and inline images."""
        html = None
        try:
            html = message.htmlBody
        except Exception:
            pass
        if html:
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="replace")
            text = self._html_to_text(html, inline)
            if text.strip():
                return text
        return (message.body or "").replace("\r\n", "\n")

    def _html_to_text(self, html: str, inline: dict) -> str:
        from bs4 import BeautifulSoup, NavigableString

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "head", "title"]):
            tag.decompose()
        for link in soup.find_all("a", href=True):
            href, label = link["href"].strip(), link.get_text(" ", strip=True)
            if href.lower().startswith("mailto:") or not href or href == label or href.startswith("#"):
                continue
            link.replace_with(NavigableString(f"{label} ({href})" if label else href))
        for img in soup.find_all("img"):
            src = img.get("src", "")
            name = inline.get(src[4:], src[4:]) if src.startswith("cid:") else (img.get("alt") or src or "image")
            img.replace_with(NavigableString(f" [inline image: {name}] "))
        for element in soup.find_all(style=True):
            color = re.search(r"(?<![-\w])color\s*:\s*([^;]+)", element["style"], flags=re.I)
            if color and color.group(1).strip().lower() not in ("black", "#000", "#000000", "windowtext", "inherit"):
                element.append(NavigableString(f" {{text: {color.group(1).strip()}}}"))
        for font in soup.find_all("font", color=True):
            font.append(NavigableString(f" {{text: {font['color']}}}"))
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):
                cells = [self._cell(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append("| " + " | ".join(cells) + " |")
            if rows:
                width = rows[0].count("|") - 1
                rows.insert(1, "|" + "---|" * width)
            table.replace_with(NavigableString("\n\n" + "\n".join(rows) + "\n\n"))
        for li in soup.find_all("li"):
            li.insert(0, NavigableString("- "))
            li.append(NavigableString("\n"))
        for br in soup.find_all("br"):
            br.replace_with(NavigableString("\n"))
        for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "tr", "ul", "ol", "hr", "blockquote"]):
            block.append(NavigableString("\n\n" if block.name in ("p", "h1", "h2", "h3", "h4", "hr") else "\n"))
        text = soup.get_text()
        text = re.sub(r"[ \t\xa0]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    # --- thread ----------------------------------------------------------------------

    HEADER_START = re.compile(r"^\*{0,2}(From|Van|Von|De|Od)\s*:", re.I)
    HEADER_NEXT = re.compile(r"^\*{0,2}(Sent|Date|Verzonden|Gesendet|Envoyé|Odoslané|Datum)\s*:", re.I)
    SEPARATOR = re.compile(r"^\s*(_{5,}|-{5,}\s*(Original Message|Forwarded message)?\s*-*|-{5,})\s*$", re.I)

    def _split_thread(self, text: str):
        """Mark each earlier email quoted in the body. Returns (text, number of earlier emails).

        Outlook quotes earlier emails under a From / Sent / To / Subject block (also in
        Dutch, German and French clients); each such block starts a new section, numbered
        from the newest earlier email.
        """
        lines = [line for line in text.split("\n") if not self.SEPARATOR.match(line)]
        starts = [i for i, line in enumerate(lines)
                  if self.HEADER_START.match(line.strip())
                  and any(self.HEADER_NEXT.match(nxt.strip()) for nxt in lines[i + 1:i + 5])]
        if not starts:
            return "\n".join(lines), 0
        out, previous = [], 0
        for number, start in enumerate(starts, start=1):
            out += lines[previous:start]
            out += ["", f"### Earlier email {number} of {len(starts)} (quoted in the thread)", ""]
            previous = start
        out += lines[previous:]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)), len(starts)

    # --- helpers ---------------------------------------------------------------------

    @staticmethod
    def _date(value) -> str:
        if value is None:
            return ""
        try:
            return value.isoformat(sep=" ", timespec="minutes")
        except AttributeError:
            return str(value)

    @staticmethod
    def _cell(text: str) -> str:
        return text.replace("|", "\\|").replace("\r", "").replace("\n", " ")

    @staticmethod
    def _safe(name: str) -> str:
        name = re.sub(r"[^\w.\-]+", "_", name).strip("_.")
        return re.sub(r"_+", "_", name) or "attachment"

    @staticmethod
    def _unique(path: Path) -> Path:
        candidate, counter = path, 2
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
            counter += 1
        return candidate
