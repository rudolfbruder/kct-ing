"""ConverterApp: a small app inside Jupyter that turns documents into PDF (no web server, no open port).

    from services.presentation.converter_app import ConverterApp
    ConverterApp()            # last line of a cell: shows the app

Choose files (Word, PDF, Excel, Outlook .msg), click Convert to PDF. A spinner shows while the
work runs. Each document gets its own bucket (a folder, see services/evidences/bucket.py) with
the PDF and every file embedded in the document; the app shows the paths and download links.

Only Word (.docx) is converted for now. The other formats are accepted by the file picker so the
whole path is visible, but they answer "not supported yet".

The work is done by plain methods (convert_file, convert_uploads), so it can be used from code
and is tested without a screen. Needs ipywidgets.
"""
from __future__ import annotations

import base64
import threading
import traceback
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional

from services.evidences.bucket import CONVERTED, FAILED, PDF, SAVED, BucketConverter, BucketItem, safe_name
from services.evidences.docx_converter import DocxConverter

UNSUPPORTED = "unsupported"

ORANGE, ORANGE_DARK, NAVY = "#FF6200", "#E55800", "#000066"

# Formats the picker accepts, and the ones that really convert today.
ACCEPTED = (".docx", ".doc", ".pdf", ".xlsx", ".xls", ".xlsm", ".msg")
WORKING = (".docx",)
FORMAT_NAMES = {".docx": "Word", ".doc": "Word (old .doc)", ".pdf": "PDF", ".xlsx": "Excel", ".xls": "Excel",
                ".xlsm": "Excel", ".msg": "Outlook email"}

# A download link carries the whole PDF inside the page, so only for files up to this size.
MAX_LINK_BYTES = 20 * 1024 * 1024

STYLE = """
<style>
.kct-conv { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; color: #111827; gap: 12px;
  max-width: 820px; }
.kct-conv .kct-card { border: 1px solid #E5E7EB; border-radius: 14px; padding: 18px 20px; background: #FFFFFF;
  box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.kct-conv .kct-head { display: flex; align-items: center; gap: 12px; }
.kct-conv .kct-logo { width: 40px; height: 40px; border-radius: 10px; background: """ + ORANGE + """;
  color: #FFFFFF; font-weight: 800; display: flex; align-items: center; justify-content: center; font-size: 15px; }
.kct-conv .kct-title { font-size: 20px; font-weight: 700; color: """ + NAVY + """; }
.kct-conv .kct-sub { color: #6B7280; font-size: 13px; margin-top: 2px; }
.kct-conv .kct-warn { background: #FFF7ED; border: 1px solid #FED7AA; color: #9A3412; border-radius: 10px;
  padding: 10px 14px; font-size: 13px; }
.kct-conv .kct-formats { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.kct-conv .kct-chip { border-radius: 999px; padding: 3px 11px; font-size: 12px; font-weight: 600; }
.kct-conv .kct-chip-on { background: #DCFCE7; color: #166534; }
.kct-conv .kct-chip-off { background: #F3F4F6; color: #9CA3AF; }
.kct-conv .kct-chip-off::after { content: " · soon"; font-weight: 500; }
.kct-conv .kct-row { gap: 10px; align-items: center; }
.kct-conv .kct-btn {
  border-radius: 9px !important; font-weight: 600 !important; font-size: 13px !important; height: 38px !important;
  padding: 0 18px !important; width: auto !important; min-width: 0 !important; border: 1px solid #D1D5DB !important;
  background: #FFFFFF !important; color: #111827 !important; box-shadow: none !important; transition: all .15s; }
.kct-conv .kct-btn:hover { background: #F9FAFB !important; border-color: #9CA3AF !important; }
.kct-conv .kct-btn-primary { background: """ + ORANGE + """ !important; border-color: """ + ORANGE + """ !important;
  color: #FFFFFF !important; }
.kct-conv .kct-btn-primary:hover { background: """ + ORANGE_DARK + """ !important; }
.kct-conv .kct-btn:disabled { opacity: .5; cursor: not-allowed; }
.kct-conv .kct-spin { display: flex; align-items: center; gap: 12px; color: #374151; font-size: 14px; }
.kct-conv .kct-spinner { width: 22px; height: 22px; border: 3px solid #FED7AA; border-top-color: """ + ORANGE + """;
  border-radius: 50%; animation: kct-conv-spin .8s linear infinite; }
@keyframes kct-conv-spin { to { transform: rotate(360deg); } }
.kct-conv .kct-result { border-radius: 10px; padding: 12px 14px; font-size: 13px; margin-top: 8px; }
.kct-conv .kct-ok { background: #F0FDF4; border: 1px solid #BBF7D0; }
.kct-conv .kct-no { background: #F9FAFB; border: 1px solid #E5E7EB; color: #4B5563; }
.kct-conv .kct-err { background: #FEF2F2; border: 1px solid #FECACA; color: #991B1B; }
.kct-conv .kct-path { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; background: #FFFFFF;
  border: 1px solid #E5E7EB; border-radius: 6px; padding: 4px 8px; display: inline-block; margin-top: 6px;
  word-break: break-all; user-select: all; }
.kct-conv a.kct-dl { display: inline-block; margin-top: 8px; background: """ + NAVY + """; color: #FFFFFF !important;
  text-decoration: none; border-radius: 8px; padding: 6px 14px; font-weight: 600; }
.kct-conv a.kct-dl:hover { background: #1A1A80; }
.kct-conv a.kct-dl-small { padding: 2px 10px; font-size: 12px; margin: 6px 0 0 6px; vertical-align: top; }
.kct-conv ul.kct-tree { list-style: none; padding-left: 18px; margin: 6px 0 0 0; border-left: 2px solid #E5E7EB; }
.kct-conv ul.kct-tree li { margin: 8px 0; }
.kct-conv .kct-note { color: #6B7280; font-size: 12px; margin-top: 3px; }
.kct-conv .kct-tag { border-radius: 999px; padding: 1px 8px; font-size: 11px; font-weight: 600; margin-left: 4px; }
.kct-conv .kct-tag-converted, .kct-conv .kct-tag-pdf { background: #DCFCE7; color: #166534; }
.kct-conv .kct-tag-saved { background: #F3F4F6; color: #4B5563; }
.kct-conv .kct-tag-failed { background: #FEE2E2; color: #991B1B; }
</style>
"""


def _uploads(value) -> List[tuple]:
    """(name, bytes) for each uploaded file; FileUpload's value differs between ipywidgets 7 and 8."""
    if isinstance(value, dict):  # ipywidgets 7: {name: {"content": bytes, ...}}
        return [(name, bytes(item["content"])) for name, item in value.items()]
    return [(item["name"], bytes(item["content"])) for item in value or ()]


class ConverterApp:
    def __init__(self, output_root: Optional[Path] = None, engine: str = "auto", show: bool = True) -> None:
        if output_root is None:
            from services.config import settings
            output_root = settings().storage_root / "converted"
        self.output_root = Path(output_root)
        self.converter = BucketConverter(DocxConverter(engine=engine))
        self.results: List[BucketItem] = []
        self._worker: Optional[threading.Thread] = None
        if show:
            self._build()

    # --- the work (no screen needed) ----------------------------------------------------

    def convert_file(self, name: str, content: bytes, folder: Optional[Path] = None) -> BucketItem:
        """Convert one uploaded file into its bucket (a folder with the PDF and the embedded files)."""
        name = safe_name(name)
        suffix = Path(name).suffix.lower()
        if suffix not in WORKING:
            kind = FORMAT_NAMES.get(suffix, suffix or "this file")
            return BucketItem(name=name, status=UNSUPPORTED,
                              error=f"{kind} is not supported yet. Only Word (.docx) is converted for now.")
        try:
            return self.converter.convert_bytes(name, content, folder or self._new_folder())
        except Exception as exc:  # shown in the app, never a crash
            return BucketItem(name=name, status=FAILED, error=f"{type(exc).__name__}: {exc}")

    def convert_uploads(self, uploads: List[tuple]) -> List[BucketItem]:
        """Convert (name, bytes) pairs; the buckets of one click go into one new folder."""
        folder = self._new_folder() if any(Path(n).suffix.lower() in WORKING for n, _ in uploads) else None
        self.results = [self.convert_file(name, content, folder) for name, content in uploads]
        return self.results

    def _new_folder(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        folder = self.output_root / stamp
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    # --- the screen ----------------------------------------------------------------------

    def _build(self) -> None:
        import ipywidgets as w

        self.w = w
        chips = "".join(
            f"<span class='kct-chip {'kct-chip-on' if s in WORKING else 'kct-chip-off'}'>{escape(FORMAT_NAMES[s])} {s}</span>"
            for s in ACCEPTED)
        header = w.HTML(
            STYLE +
            "<div class='kct-card'><div class='kct-head'><div class='kct-logo'>PDF</div><div>"
            "<div class='kct-title'>Document to PDF</div>"
            "<div class='kct-sub'>Choose a document, convert it, download the PDF. Files embedded in the document "
            "are taken out too. Nothing leaves this machine.</div>"
            "</div></div>"
            "<div class='kct-warn' style='margin-top:14px'><b>Only Word (.docx) works for now.</b> "
            "PDF, Excel and Outlook (.msg) files can be chosen, but they are not converted yet. "
            "Files embedded in a Word document are all saved in its bucket; the embedded Word documents "
            "are converted too.</div>"
            f"<div class='kct-formats'>{chips}</div></div>")
        self.upload = w.FileUpload(accept=",".join(ACCEPTED), multiple=True, description="Choose files")
        self.convert_button = w.Button(description="Convert to PDF", icon="file-pdf-o")
        self.upload.add_class("kct-btn")
        self.convert_button.add_class("kct-btn")
        self.convert_button.add_class("kct-btn-primary")
        self.convert_button.on_click(lambda _: self.start())
        self.status = w.HTML("")
        actions = w.HBox([self.upload, self.convert_button])
        actions.add_class("kct-row")
        body = w.VBox([actions, self.status])
        body.add_class("kct-card")
        self.box = w.VBox([header, body])
        self.box.add_class("kct-conv")

    def start(self) -> None:
        """Button click: show the spinner, convert in the background so the spinner keeps turning."""
        uploads = _uploads(self.upload.value)
        if not uploads:
            self.status.value = "<div class='kct-result kct-no'>Choose a file first.</div>"
            return
        if self._worker and self._worker.is_alive():
            return
        names = ", ".join(escape(n) for n, _ in uploads)
        self.status.value = (f"<div class='kct-spin'><div class='kct-spinner'></div>"
                             f"<div>Converting {names} …</div></div>")
        self.convert_button.disabled = True
        self.upload.disabled = True
        self._worker = threading.Thread(target=self._run, args=(uploads,), daemon=True)
        self._worker.start()

    def _run(self, uploads: List[tuple]) -> None:
        try:
            self.status.value = self.render(self.convert_uploads(uploads))
        except Exception:
            self.status.value = f"<div class='kct-result kct-err'><pre>{escape(traceback.format_exc())}</pre></div>"
        finally:
            self.convert_button.disabled = False
            self.upload.disabled = False
            try:
                self.upload.value = ()      # ipywidgets 8; ready for the next file
            except Exception:
                pass

    @staticmethod
    def render(results: List[BucketItem]) -> str:
        """HTML for the results: per document its bucket, the PDF, and every embedded file."""
        budget = [MAX_LINK_BYTES * 2]     # download links of one click carry at most this much

        def link(pdf: Path) -> str:
            size = pdf.stat().st_size
            if size > MAX_LINK_BYTES or size > budget[0]:
                return ""
            budget[0] -= size
            data = base64.b64encode(pdf.read_bytes()).decode("ascii")
            return (f" <a class='kct-dl kct-dl-small' download='{escape(pdf.name)}' "
                    f"href='data:application/pdf;base64,{data}'>Download</a>")

        def path(p: Path, base: Optional[Path] = None) -> str:
            shown = str(p)
            if base is not None:
                try:
                    shown = p.relative_to(base).as_posix()
                except ValueError:
                    pass
            return f"<span class='kct-path' title='{escape(str(p))}'>{escape(shown)}</span>"

        def tree(items: List[BucketItem], base: Path) -> str:
            rows = []
            for c in items:
                icon = {CONVERTED: "📄", PDF: "📄", SAVED: "📎", FAILED: "❌"}.get(c.status, "•")
                label = {CONVERTED: "converted to PDF", PDF: "already a PDF", SAVED: "saved", FAILED: "failed"}[c.status]
                where = path(c.pdf, base) + link(c.pdf) if c.pdf else path(c.source, base) if c.source else ""
                note = f"<div class='kct-note'>{escape(c.error)}</div>" if c.error else ""
                rows.append(f"<li>{icon} <b>{escape(c.name)}</b> <span class='kct-tag kct-tag-{c.status}'>{label}</span>"
                            f"<br>{where}{note}{tree(c.children, base) if c.children else ''}</li>")
            return f"<ul class='kct-tree'>{''.join(rows)}</ul>"

        parts = []
        for r in results:
            if r.status == UNSUPPORTED:
                parts.append(f"<div class='kct-result kct-no'>⏳ <b>{escape(r.name)}</b>: {escape(r.error)}</div>")
                continue
            if r.folder is None:
                parts.append(f"<div class='kct-result kct-err'>❌ <b>{escape(r.name)}</b> failed: {escape(r.error)}</div>")
                continue
            embedded = sum(1 for _ in r.walk()) - 1
            head = (f"✅ <b>{escape(r.name)}</b> converted <span style='color:#6B7280'>"
                    f"({r.pdf.stat().st_size / 1024:.0f} KB, engine: {escape(r.engine)})</span>"
                    if r.pdf else f"❌ <b>{escape(r.name)}</b>: the document itself failed: {escape(r.error)}")
            parts.append(
                f"<div class='kct-result {'kct-ok' if r.pdf else 'kct-err'}'>{head}"
                f"<div style='margin-top:8px'>Bucket (everything for this document):<br>{path(r.folder)}</div>"
                + (f"<div style='margin-top:8px'>PDF:<br>{path(r.pdf)}{link(r.pdf)}</div>" if r.pdf else "")
                + (f"<div style='margin-top:10px'><b>Embedded files ({embedded})</b>"
                   f"<div class='kct-note'>Paths inside the bucket.</div>{tree(r.children, r.folder)}</div>"
                   if r.children else "<div class='kct-note' style='margin-top:8px'>No embedded files.</div>")
                + "</div>")
        return "".join(parts)

    def _ipython_display_(self) -> None:
        from IPython.display import display
        display(self.box)
