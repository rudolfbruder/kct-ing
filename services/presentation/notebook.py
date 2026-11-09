"""Visual building blocks for the notebooks and the app: HTML that renders in JupyterLab and VS Code.

Every function returns an IPython HTML object (display it, or leave it last in a cell).
Colors are set inline on white cards, so they read the same in light and dark themes.

    from services.presentation import notebook as show
    show.banner("Key Control Testing", "From the control documents to test steps")
    show.test_steps(interpretation)
"""
from __future__ import annotations

import re
from html import escape
from typing import Iterable, List, Optional

GREEN, GREEN_BG = "#166534", "#DCFCE7"
RED, RED_BG = "#991B1B", "#FEE2E2"
AMBER, AMBER_BG = "#92400E", "#FEF3C7"
BLUE, BLUE_BG = "#000066", "#E6E6F5"       # ING navy
ORANGE, ORANGE_BG = "#FF6200", "#FFF1E6"   # ING orange
GREY, GREY_BG = "#4B5563", "#F3F4F6"
INK = "#111827"
CARD = f"background:#FFFFFF;color:{INK};border:1px solid #E5E7EB;border-radius:10px;padding:14px 16px;" \
       "font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:13px;line-height:1.45;"


# Jupyter's own table style right-aligns cells; this (scoped to our output) puts them back,
# and keeps cards shown one after another apart.
STYLE = ("<style>div.kct table td,div.kct table th{text-align:left;vertical-align:top;padding:3px 8px}"
         "div.kct table{margin:0}div.kct ul{margin:4px 0 8px 18px;padding:0}"
         "div.kct{margin:0 0 14px 0}"   # space between cards shown one after another
         # loaders: a spinning ring and grey "skeleton" bars with a moving shine
         "@keyframes kct-spin{to{transform:rotate(360deg)}}"
         "@keyframes kct-shine{0%{background-position:-600px 0}100%{background-position:600px 0}}"
         ".kct-spinner{display:inline-block;width:16px;height:16px;border:3px solid #FFE0CC;"
         "border-top-color:#FF6200;border-radius:50%;animation:kct-spin .8s linear infinite;vertical-align:middle}"
         ".kct-spinner-lg{width:34px;height:34px;border-width:4px}"
         ".kct-skeleton{height:12px;border-radius:6px;margin:9px 0;background:linear-gradient(90deg,#F3F4F6 25%,"
         "#E5E7EB 37%,#F3F4F6 63%);background-size:1200px 100%;animation:kct-shine 1.4s ease infinite}"
         "</style>")


def _left_align(markup: str) -> str:
    """Inline text-align:left on every table cell that sets no alignment (Jupyter's CSS right-aligns them)."""
    def fix(match):
        tag, attributes = match.group(1), match.group(2)
        if "text-align" in attributes or "align=" in attributes:
            return match.group(0)
        if "style='" in attributes:
            return f"<{tag}{attributes.replace(chr(39).join(['style=', '']), 'style=' + chr(39) + 'text-align:left;', 1)}>"
        return f"<{tag}{attributes} style='text-align:left'>"

    return re.sub(r"<(td|th)(\b[^>]*)>", fix, markup)


# Small line icons (24x24, drawn with the text color unless one is given), inlined as SVG: no files, no CDN.
ICONS = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder-plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
                   '<path d="M12 11v6M9 14h6"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "upload": '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="M10 8.5l5 3.5-5 3.5z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    "x": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "alert": '<path d="M12 3.5l9 15.5H3z"/><path d="M12 10v4M12 17h.01"/>',
    "pointer": '<path d="M8 3v13l3.5-3.5L14 18l2.5-1-2.5-5.5H19z"/>',
    "spark": '<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
}


def svg(name: str, color: str = "currentColor", size: int = 16) -> str:
    """An icon from ICONS as inline SVG markup, aligned with the text around it."""
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' stroke='{color}' stroke-width='2' "
            f"stroke-linecap='round' stroke-linejoin='round' style='vertical-align:-3px;flex:none'>"
            f"{ICONS[name]}</svg>")


def _html(markup: str):
    from IPython.display import HTML

    return HTML(f"{STYLE}<div class='kct'>{_left_align(markup)}</div>")


def quiet() -> None:
    """Keep the log lines out of the notebook (they still go to storage/logs)."""
    import logging

    for name in ("kct", "kct.ai"):
        for handler in logging.getLogger(name).handlers:
            if type(handler) is logging.StreamHandler:
                handler.setLevel(logging.WARNING)


def _badge(text: str, color: str, background: str) -> str:
    return (f"<span style='background:{background};color:{color};border-radius:999px;padding:2px 9px;"
            f"font-size:11px;font-weight:600;white-space:nowrap'>{escape(text)}</span>")


def _verdict_badge(verdict: str, no_evidence: bool = False) -> str:
    if verdict == "effective":
        return _badge("EFFECTIVE", GREEN, GREEN_BG)
    return _badge("NO EVIDENCE", AMBER, AMBER_BG) if no_evidence else _badge("NOT EFFECTIVE", RED, RED_BG)


# --- headings and status -------------------------------------------------------------------

def _logo_html(height: int = 34) -> str:
    """The brand's logo as an inline image, or its name as a wordmark when the file is not there."""
    import base64

    from services.branding import brand

    b = brand()
    if b.logo:
        data = base64.b64encode(b.logo.read_bytes()).decode("ascii")
        kind = "svg+xml" if b.logo.suffix.lower() == ".svg" else b.logo.suffix.lower().lstrip(".") or "png"
        return f"<img src='data:image/{kind};base64,{data}' style='height:{height}px' alt='{escape(b.name)}'>"
    return f"<span style='font-size:{height - 6}px;font-weight:800;color:{ORANGE}'>{escape(b.name)}</span>"


def banner(title: str, subtitle: str = ""):
    return _html(
        f"<div style='background:#FFFFFF;color:{BLUE};border-radius:12px;border:1px solid #E5E7EB;"
        f"border-top:6px solid {ORANGE};padding:18px 24px;display:flex;justify-content:space-between;"
        f"align-items:center;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif'>"
        f"<div><div style='font-size:24px;font-weight:700;color:{BLUE}'>{escape(title)}</div>"
        f"<div style='font-size:14px;color:{GREY};margin-top:4px'>{escape(subtitle)}</div></div>"
        f"<div>{_logo_html()}</div></div>")


def mode(provider: str, model: str, replay: str = ""):
    if provider == "fake":
        text, color, bg = "FAKE AI: fixed sample answers, no AI called", AMBER, AMBER_BG
    else:
        text, color, bg = f"LIVE AI: {provider} / {model}", GREEN, GREEN_BG
    return _html(f"<div style='{CARD}'>{svg('spark', color)} Mode: {_badge(text, color, bg)}</div>")


def notice(text: str, kind: str = "info"):
    color, bg = {"info": (BLUE, BLUE_BG), "ok": (GREEN, GREEN_BG), "warn": (AMBER, AMBER_BG),
                 "error": (RED, RED_BG)}[kind]
    icon = {"info": "info", "ok": "check", "warn": "alert", "error": "x"}[kind]
    return _html(f"<div style='{CARD}border-left:5px solid {color};background:{bg};color:{INK};display:flex;gap:10px;"
                 f"align-items:flex-start'>{svg(icon, color, 18)}<div>{escape(text)}</div></div>")


def loading(text: str, rows: int = 4):
    """A card that shows work is going on: spinner, text, and skeleton bars where the result will appear."""
    widths = [92, 76, 84, 60, 88, 70]
    bars = "".join(f"<div class='kct-skeleton' style='width:{widths[i % len(widths)]}%;margin:9px auto'></div>" for i in range(rows))
    return _html(f"<div style='{CARD}min-height:240px;display:flex;flex-direction:column;align-items:center;"
                 f"justify-content:center;gap:14px'><span class='kct-spinner kct-spinner-lg'></span>"
                 f"<div style='font-weight:600;text-align:center'>{escape(text)}</div>"
                 f"<div style='width:100%;max-width:640px'>{bars}</div></div>")


def _icon(name: str) -> str:
    suffix = name.lower().rsplit(".", 1)[-1]
    return {"docx": "📝", "xlsx": "📊", "xlsm": "📊", "msg": "✉️", "pdf": "📕", "png": "🖼️", "jpg": "🖼️",
            "zip": "🗜️", "md": "📄", "txt": "📄"}.get(suffix, "📄")


def sorting(result):
    """What the import decided for each file."""
    rows = []
    # a flat ZIP lists every file it sorted; a folder import lists its two documents
    items = result.sorted_by_ai or [*result.control_details, *result.test_plan, *result.other]
    for item in items:
        color, bg = {"control_details": (BLUE, BLUE_BG), "test_plan": (GREEN, GREEN_BG),
                     "evidence": (GREY, GREY_BG), "other": (AMBER, AMBER_BG)}[item.role]
        rows.append(f"<tr><td>{_icon(item.name)} {escape(item.name)}</td>"
                    f"<td>{_badge(item.role.replace('_', ' '), color, bg)}</td>"
                    f"<td style='color:{GREY}'>{escape(item.reason)} "
                    f"<i>({'set by hand' if item.by == 'override' else 'AI' if item.role != 'evidence' else 'rule'})</i></td></tr>")
    evidence = "".join(f"<div>{_icon(p)} {escape(p)}</div>" for p in result.evidence)
    skipped = "".join(f"<div style='color:{GREY}'>⏭ {escape(s.path)}: {escape(s.reason)}</div>" for s in result.skipped)
    return _html(
        f"<div style='{CARD}'><div style='font-weight:700;margin-bottom:6px'>Documents sorted</div>"
        f"<table style='border-collapse:collapse;width:100%'>{''.join(rows)}</table>"
        f"<div style='font-weight:700;margin:10px 0 4px'>Evidence for the case ({len(result.evidence)})</div>"
        f"{evidence}{skipped}</div>")


# --- interpretation and evidence --------------------------------------------------------------

def test_steps(interpretation, limit: int = 30):
    rows = "".join(
        f"<tr><td style='white-space:nowrap;font-weight:600'>{escape(s.reference)}</td><td>{escape(s.title)}</td>"
        f"<td style='text-align:center;white-space:nowrap'>{svg('check', GREEN)} {len(s.acceptance_criteria)}</td>"
        f"<td style='text-align:center;white-space:nowrap'>{svg('x', RED)} {len(s.refusal_criteria)}</td></tr>"
        for s in interpretation.test_steps[:limit])
    return _html(
        f"<div style='{CARD}'><div style='font-weight:700;margin-bottom:6px'>"
        f"{svg('list', ORANGE)} {len(interpretation.test_steps)} test steps from the control details and test plan</div>"
        f"<table style='border-collapse:collapse;width:100%'><tr style='color:{GREY}'><th>Step</th>"
        f"<th>What it checks</th><th>Acceptance criteria</th><th>Refusal criteria</th></tr>{rows}</table></div>")


def criteria(step):
    """One test step with all its criteria."""
    def lines(items, icon, color):
        return "".join(f"<div style='display:flex;gap:8px;margin:5px 0 5px 4px'>{svg(icon, color)}"
                       f"<div>{escape(c)}</div></div>" for c in items)

    accept = lines(step.acceptance_criteria, "check", GREEN)
    refuse = lines(step.refusal_criteria, "x", RED)
    return _html(
        f"<div style='{CARD}'><div style='font-weight:700;font-size:15px'>{svg('list', ORANGE)} "
        f"{escape(step.reference)}: {escape(step.title)}</div>"
        f"<div style='color:{GREY};margin:4px 0 8px'>{escape(step.description)}</div>"
        f"<div style='color:{GREEN};font-weight:600;margin-top:6px'>Passes only if all hold</div>{accept}"
        f"<div style='color:{RED};font-weight:600;margin-top:10px'>Fails if any is true</div>{refuse}</div>")


# --- progress -------------------------------------------------------------------------------

class Progress:
    """A progress bar that follows the assessment's progress messages ("[3/6] ...")."""

    def __init__(self, title: str = "Assessment") -> None:
        from IPython.display import display

        self.title = title
        self.done, self.total, self.last = 0, 0, "starting …"
        self.lines: List[str] = []
        self.handle = display(self._render(), display_id=True)

    def __call__(self, message: str) -> None:
        match = re.match(r"\[(\d+)/(\d+)\]", message.strip())
        if match:
            self.done, self.total = int(match.group(1)) - 1, int(match.group(2))
        if message.strip().startswith(("✅", "❌")) and self.total:
            self.done = min(self.total, self.done + 1) if "relevant step" in message or "❌" in message else self.done
        self.last = message.strip()
        self.lines.append(message.rstrip())
        if self.handle is None:   # not in a live notebook (script, test): plain lines instead
            print(message)
        else:
            self.handle.update(self._render())

    def _render(self):
        share = 100 * self.done / self.total if self.total else 0
        log = escape("\n".join(self.lines[-8:]))
        return _html(
            f"<div style='{CARD}'><div style='font-weight:700'>"
            + ("" if self.total and self.done >= self.total else "<span class='kct-spinner'></span> ")
            + f"{escape(self.title)}</div>"
            f"<div style='background:{GREY_BG};border-radius:6px;height:12px;margin:8px 0'>"
            f"<div style='background:{ORANGE};width:{share:.0f}%;height:12px;border-radius:6px'></div></div>"
            f"<div style='color:{GREY}'>{self.done} of {self.total or '?'} evidence parts</div>"
            f"<pre style='font-size:11px;color:{INK};background:{GREY_BG};padding:8px;border-radius:6px;"
            f"white-space:pre-wrap;margin-top:8px'>{log}</pre></div>")


# --- results --------------------------------------------------------------------------------

def verdict_card(verdict, step=None):
    exceptions = "".join(
        f"<div style='background:{RED_BG};border-radius:8px;padding:8px 10px;margin:6px 0'>"
        f"<b>{escape(e.item)}</b>: {escape(e.description)}"
        + (f"<div style='color:{GREY};font-size:12px;margin-top:3px'>📍 {escape(e.reference.document)}"
           f"{', ' + escape(e.reference.location) if e.reference.location else ''}</div>" if e.reference else "")
        + "</div>" for e in verdict.exceptions)
    refs = "".join(f"<div style='color:{GREY};font-size:12px'>📍 {escape(r.document)}"
                   f"{', ' + escape(r.location) if r.location else ''}</div>" for r in verdict.references
                   if not verdict.exceptions)
    problems = "".join(f"<div style='color:{RED};font-size:12px'>⚠ {escape(p)}</div>"
                       for p in verdict.reference_problems)
    description = f"<div style='color:{GREY};margin:4px 0'>{escape(step.description)}</div>" if step else ""
    return _html(
        f"<div style='{CARD}'><div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<div style='font-size:15px;font-weight:700'>{escape(verdict.step_reference)}: {escape(verdict.title)}</div>"
        f"{_verdict_badge(verdict.verdict, verdict.no_evidence)}</div>{description}"
        f"<div style='margin:8px 0'>{escape(verdict.reason)}</div>{exceptions}{refs}{problems}</div>")


def report_link(path: str, sha256: str = ""):
    return _html(f"<div style='{CARD}'>📕 <b>Read-only PDF report</b><div style='font-family:Menlo,Consolas,monospace;"
                 f"font-size:12px;margin-top:4px'>{escape(path)}</div>"
                 + (f"<div style='color:{GREY};font-size:11px'>SHA-256 {escape(sha256)}</div>" if sha256 else "")
                 + "</div>")
