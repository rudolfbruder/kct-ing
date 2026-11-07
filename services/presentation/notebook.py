"""Visual building blocks for the demo notebook: HTML that renders in JupyterLab and VS Code.

Every function returns an IPython HTML object (display it, or leave it last in a cell).
Colors are set inline on white cards, so they read the same in light and dark themes.

    from services.presentation import notebook as show
    show.banner("Key Control Testing", "From SharePoint folder to verdict")
    show.kpis(assessment)
    show.matrix(assessment)
"""
from __future__ import annotations

import re
from html import escape
from pathlib import Path
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


# Jupyter's own table style right-aligns cells; this (scoped to our output) puts them back.
STYLE = ("<style>div.kct table td,div.kct table th{text-align:left;vertical-align:top;padding:3px 8px}"
         "div.kct table{margin:0}div.kct ul{margin:4px 0 8px 18px;padding:0}</style>")


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


def step(number: int, title: str, text: str = ""):
    return _html(
        f"<div style='font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;margin:6px 0'>"
        f"<span style='display:inline-block;background:{ORANGE};color:#FFF;border-radius:999px;width:26px;"
        f"height:26px;text-align:center;line-height:26px;font-weight:700;margin-right:8px'>{number}</span>"
        f"<span style='font-size:17px;font-weight:700;color:{BLUE}'>{escape(title)}</span>"
        f"<div style='color:{GREY};margin:4px 0 0 34px'>{escape(text)}</div></div>")


def mode(provider: str, model: str, replay: str = ""):
    if provider == "replay":
        text, color, bg = f"REPLAY of recorded real AI answers ({replay})", BLUE, BLUE_BG
    elif provider == "fake":
        text, color, bg = "FAKE AI: fixed sample answers, no AI called", AMBER, AMBER_BG
    else:
        text, color, bg = f"LIVE AI: {provider} / {model}", GREEN, GREEN_BG
    return _html(f"<div style='{CARD}'>Mode: {_badge(text, color, bg)}</div>")


def notice(text: str, kind: str = "info"):
    color, bg = {"info": (BLUE, BLUE_BG), "ok": (GREEN, GREEN_BG), "warn": (AMBER, AMBER_BG),
                 "error": (RED, RED_BG)}[kind]
    return _html(f"<div style='{CARD}border-left:5px solid {color};background:{bg};color:{INK}'>{escape(text)}</div>")


# --- input ----------------------------------------------------------------------------------

def tree(folder, limit: int = 40):
    """A folder as an indented tree (files and folders)."""
    folder = Path(folder)
    lines: List[str] = []
    for path in sorted(folder.rglob("*")):
        if path.name.startswith((".", "~$")):
            continue
        depth = len(path.relative_to(folder).parts) - 1
        icon = "📁" if path.is_dir() else _icon(path.name)
        lines.append(f"<div style='padding-left:{depth * 18}px'>{icon} {escape(path.name)}</div>")
        if len(lines) >= limit:
            lines.append("<div>…</div>")
            break
    return _html(f"<div style='{CARD}font-family:Menlo,Consolas,monospace;font-size:12px'>"
                 f"<b>{escape(folder.name)}/</b>{''.join(lines)}</div>")


def _icon(name: str) -> str:
    suffix = name.lower().rsplit(".", 1)[-1]
    return {"docx": "📝", "xlsx": "📊", "xlsm": "📊", "msg": "✉️", "pdf": "📕", "png": "🖼️", "jpg": "🖼️",
            "zip": "🗜️", "md": "📄", "txt": "📄"}.get(suffix, "📄")


def sorting(result):
    """What the import decided for each file."""
    rows = []
    for item in [*result.control_details, *result.test_plan, *result.other, *result.sorted_by_ai]:
        color, bg = {"control_details": (BLUE, BLUE_BG), "test_plan": (GREEN, GREEN_BG),
                     "evidence": (GREY, GREY_BG), "other": (AMBER, AMBER_BG)}[item.role]
        rows.append(f"<tr><td>{_icon(item.name)} {escape(item.name)}</td>"
                    f"<td>{_badge(item.role.replace('_', ' '), color, bg)}</td>"
                    f"<td style='color:{GREY}'>{escape(item.reason)} "
                    f"<i>({'set by hand' if item.by == 'override' else 'AI'})</i></td></tr>")
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
        f"<td style='text-align:center'>{len(s.acceptance_criteria)}</td>"
        f"<td style='text-align:center'>{len(s.refusal_criteria)}</td></tr>"
        for s in interpretation.test_steps[:limit])
    return _html(
        f"<div style='{CARD}'><div style='font-weight:700;margin-bottom:6px'>"
        f"{len(interpretation.test_steps)} test steps from the control details and test plan</div>"
        f"<table style='border-collapse:collapse;width:100%'><tr style='color:{GREY}'><th>Step</th>"
        f"<th>What it checks</th><th>Acceptance criteria</th><th>Refusal criteria</th></tr>{rows}</table></div>")


def criteria(step):
    """One test step with all its criteria."""
    accept = "".join(f"<li>{escape(c)}</li>" for c in step.acceptance_criteria)
    refuse = "".join(f"<li>{escape(c)}</li>" for c in step.refusal_criteria)
    return _html(
        f"<div style='{CARD}'><div style='font-weight:700'>{escape(step.reference)}: {escape(step.title)}</div>"
        f"<div style='color:{GREY};margin:4px 0 8px'>{escape(step.description)}</div>"
        f"<div style='color:{GREEN};font-weight:600'>Passes only if all hold</div><ul>{accept}</ul>"
        f"<div style='color:{RED};font-weight:600'>Fails if any is true</div><ul>{refuse}</ul></div>")


def excel_preview(markdown_text: str, columns: int = 11, normal_rows: int = 3):
    """The first sheet of a converted workbook: header, a few rows, and every colored row."""
    lines = markdown_text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("| Row |")), None)
    if start is None:
        return notice("No table found in this workbook text.", "warn")
    header = [c.strip() for c in lines[start].strip("|").split("|")][:columns + 1]
    body, shown_normal = [], 0
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        colored = "{row fill:" in cells[0]
        if not colored and shown_normal >= normal_rows:
            continue
        shown_normal += not colored
        background = RED_BG if "light red" in cells[0] else (AMBER_BG if colored else "#FFFFFF")
        tds = []
        for cell in cells[:columns + 1]:
            notes = re.findall(r"\{([^}]*)\}", cell)
            value = escape(re.sub(r"\s*\{[^}]*\}", "", cell))
            marks = "".join(f"<div style='font-size:10px;color:{RED if 'red' in n else GREY}'>{escape(n)}</div>"
                            for n in notes if not n.startswith("merged"))
            tds.append(f"<td style='border:1px solid #E5E7EB;padding:2px 5px'>{value}{marks}</td>")
        body.append(f"<tr style='background:{background}'>{''.join(tds)}</tr>")
    heads = "".join(f"<th style='border:1px solid #E5E7EB;padding:2px 5px;background:{GREY_BG}'>{escape(h)}</th>"
                    for h in header)
    return _html(f"<div style='{CARD}overflow-x:auto'><div style='font-weight:700;margin-bottom:6px'>"
                 f"What the AI reads from the workbook (first {columns} columns; colored rows kept with their color)"
                 f"</div><table style='border-collapse:collapse;font-size:11px'><tr>{heads}</tr>{''.join(body)}"
                 f"</table></div>")


def markdown(text: str, max_lines: int = 60):
    from IPython.display import Markdown

    lines = text.split("\n")
    return Markdown("\n".join(lines[:max_lines]) + ("\n\n…" if len(lines) > max_lines else ""))


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
        self.handle.update(self._render())

    def _render(self):
        share = 100 * self.done / self.total if self.total else 0
        log = escape("\n".join(self.lines[-8:]))
        return _html(
            f"<div style='{CARD}'><div style='font-weight:700'>{escape(self.title)}</div>"
            f"<div style='background:{GREY_BG};border-radius:6px;height:12px;margin:8px 0'>"
            f"<div style='background:{ORANGE};width:{share:.0f}%;height:12px;border-radius:6px'></div></div>"
            f"<div style='color:{GREY}'>{self.done} of {self.total or '?'} evidence parts</div>"
            f"<pre style='font-size:11px;color:{INK};background:{GREY_BG};padding:8px;border-radius:6px;"
            f"white-space:pre-wrap;margin-top:8px'>{log}</pre></div>")


# --- results --------------------------------------------------------------------------------

def kpis(assessment, currency: str = ""):
    meta, verdicts = assessment.metadata, assessment.verdicts
    effective = sum(v.verdict == "effective" for v in verdicts)
    no_evidence = sum(v.no_evidence for v in verdicts)
    boxes = [(effective, "effective", GREEN), (len(verdicts) - effective, "not effective", RED),
             (no_evidence, "without evidence", AMBER), (meta.evidence_files, "evidence files", BLUE)]
    cells = "".join(f"<div style='flex:1;text-align:center;padding:6px'><div style='font-size:34px;font-weight:800;"
                    f"color:{c}'>{n}</div><div style='color:{GREY}'>{escape(l)}</div></div>" for n, l, c in boxes)
    facts = [f"{len(verdicts)} test steps", f"{meta.parts_total} evidence parts"]
    if meta.duration_seconds is not None:
        facts.append(f"{meta.duration_seconds:.0f} s run time")
    if meta.input_tokens or meta.output_tokens:
        facts.append(f"{meta.input_tokens + meta.output_tokens:,} tokens")
    if meta.estimated_cost is not None:
        facts.append(f"cost {meta.estimated_cost:.2f} {currency}")
    facts.append(f"model {meta.model}")
    return _html(f"<div style='{CARD}'><div style='display:flex;gap:8px'>{cells}</div>"
                 f"<div style='color:{GREY};text-align:center;margin-top:6px'>{escape(' · '.join(facts))}</div></div>")


def matrix(assessment):
    from services.assessment.matrix import Matrix, traceability

    data = traceability(assessment)
    styles = {"supports": ("✓", GREEN, GREEN_BG), "contradicts": ("✗", RED, RED_BG), "partly": ("◐", AMBER, AMBER_BG),
              "not_relevant": ("", GREY, "#FFFFFF"), "failed": ("?", GREY, GREY_BG)}
    heads = "".join(f"<th title='{escape(u)}' style='padding:4px 8px;background:{GREY_BG}'>{escape(Matrix.short(u))}</th>"
                    for u in data.units)
    rows = []
    for row in data.rows:
        cells = "".join(
            f"<td style='text-align:center;background:{styles[row.cells[u]][2]};color:{styles[row.cells[u]][1]};"
            f"font-weight:700;border:1px solid #E5E7EB'>{styles[row.cells[u]][0]}</td>" for u in data.units)
        rows.append(f"<tr><td style='padding:3px 8px;border:1px solid #E5E7EB;white-space:nowrap'>"
                    f"<b>{escape(row.step_reference)}</b> <span style='color:{GREY}'>{escape(row.title)}</span></td>"
                    f"<td style='padding:3px 8px;border:1px solid #E5E7EB'>{_verdict_badge(row.verdict, row.no_evidence)}"
                    f"</td>{cells}</tr>")
    legend = (f"{_badge('✓ supports', GREEN, GREEN_BG)} {_badge('✗ contradicts', RED, RED_BG)} "
              f"{_badge('◐ partly', AMBER, AMBER_BG)} {_badge('? not assessed', GREY, GREY_BG)} "
              f"<span style='color:{GREY}'>empty = says nothing about the step</span>")
    names = " · ".join(f"<b>{escape(Matrix.short(u))}</b> {escape(u)}" for u in data.units)
    return _html(
        f"<div style='{CARD}overflow-x:auto'><div style='font-weight:700;margin-bottom:6px'>"
        f"Traceability: what each evidence file shows for each test step</div>"
        f"<table style='border-collapse:collapse'><tr><th style='padding:4px 8px;background:{GREY_BG}'>"
        f"Test step</th><th style='padding:4px 8px;background:{GREY_BG}'>Verdict</th>{heads}</tr>{''.join(rows)}"
        f"</table><div style='margin-top:8px'>{legend}</div>"
        f"<div style='color:{GREY};font-size:11px;margin-top:6px'>{names}</div></div>")


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


def trust(assessment, runs: int = 1):
    """The guardrails, with this run's numbers."""
    parts = assessment.parts
    references = sum(len([c for c in f.criteria if c.reference]) + len([e for e in f.exceptions if e.reference])
                     for p in parts for f in p.findings)
    problems = sum(len(f.reference_problems) for p in parts for f in p.findings) + \
        sum(len(v.reference_problems) for v in assessment.verdicts)
    fallback = sum(v.fallback for v in assessment.verdicts)
    failed = sum(p.status == "failed" for p in parts)
    meta = assessment.metadata
    items = [
        ("🔎", f"{references} evidence references checked against the documents sent; {problems} flagged",
         "The AI must cite document, page, sheet/row or email; a citation that does not exist is flagged, never hidden."),
        ("⚖️", "Missing evidence means not effective",
         "No relevant evidence → not effective, flagged 'no evidence'. A step the AI skips → not effective, flagged 'fallback'"
         f" ({fallback} in this run)."),
        ("🧩", f"{len(parts)} evidence parts, {failed} failed",
         "Big files are split so nothing is skimmed; a part that fails is recorded and shown, the run continues."),
        ("🔒", "Read-only report with fingerprints",
         f"PDF without edit rights; SHA-256 of the report ({(meta.report_sha256 or '')[:16]}…) and of every evidence file stored."),
        ("🗂️", f"{runs} run(s) kept for this control",
         "Every run is stored with its model, inputs and results; nothing is overwritten."),
        ("🇪🇺", "Data stays in the bank's own Google project",
         "Gemini on Vertex AI in an EU region; no data goes to a public AI service."),
    ]
    rows = "".join(f"<div style='display:flex;gap:10px;margin:7px 0'><div style='font-size:20px'>{i}</div>"
                   f"<div><b>{escape(t)}</b><div style='color:{GREY}'>{escape(d)}</div></div></div>"
                   for i, t, d in items)
    return _html(f"<div style='{CARD}'><div style='font-weight:700;margin-bottom:4px'>Why the result can be trusted"
                 f"</div>{rows}</div>")


def savings(assessment, manual_hours: Optional[float], hourly_rate: Optional[float] = None, currency: str = ""):
    meta = assessment.metadata
    minutes = (meta.duration_seconds or 0) / 60
    if manual_hours is None:
        body = (f"<div>KCT run: <b>{minutes:.1f} min</b>"
                + (f", <b>{meta.estimated_cost:.2f} {escape(currency)}</b> AI cost" if meta.estimated_cost is not None else "")
                + f"</div><div style='color:{AMBER};margin-top:6px'>Set MANUAL_HOURS (your estimate of manual testing time "
                  "for this control) to show the comparison.</div>")
    else:
        saved = manual_hours - minutes / 60
        body = (f"<div style='display:flex;gap:8px;text-align:center'>"
                f"<div style='flex:1'><div style='font-size:30px;font-weight:800;color:{GREY}'>{manual_hours:g} h</div>"
                f"<div style='color:{GREY}'>manual testing (your estimate)</div></div>"
                f"<div style='flex:1'><div style='font-size:30px;font-weight:800;color:{BLUE}'>{minutes:.1f} min</div>"
                f"<div style='color:{GREY}'>KCT run, before review</div></div>"
                f"<div style='flex:1'><div style='font-size:30px;font-weight:800;color:{GREEN}'>{saved:.1f} h</div>"
                f"<div style='color:{GREY}'>freed for review and judgement</div></div></div>")
        if hourly_rate:
            body += (f"<div style='color:{GREY};text-align:center;margin-top:6px'>≈ {saved * hourly_rate:,.0f} "
                     f"{escape(currency)} per control at {hourly_rate:g}/h"
                     + (f", AI cost {meta.estimated_cost:.2f}" if meta.estimated_cost is not None else "") + "</div>")
    return _html(f"<div style='{CARD}'><div style='font-weight:700;margin-bottom:6px'>Time</div>{body}"
                 f"<div style='color:{GREY};font-size:11px;margin-top:8px'>A tester still reviews the verdicts; "
                 f"KCT prepares them with evidence references.</div></div>")


def report_link(path: str, sha256: str = ""):
    return _html(f"<div style='{CARD}'>📕 <b>Read-only PDF report</b><div style='font-family:Menlo,Consolas,monospace;"
                 f"font-size:12px;margin-top:4px'>{escape(path)}</div>"
                 + (f"<div style='color:{GREY};font-size:11px'>SHA-256 {escape(sha256)}</div>" if sha256 else "")
                 + "</div>")
