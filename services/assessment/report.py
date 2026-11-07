"""AssessmentReport: the read-only PDF of one assessment.

    pdf_bytes = AssessmentReport(assessment, interpretation).build()

Contents:
    0. Executive summary (page 1): verdict counts, run figures, the traceability matrix
       (test steps x evidence files) and the key exceptions
    1. Header: case, assessment ID, interpretation, model, dates, evidence parts
    2. Summary: one line per test step with its verdict (and "no evidence" / "fallback")
    3. Per test step: description, criteria, verdict, reason, exceptions, references
    4. Evidence: every file with its SHA-256 and how many parts were assessed or failed
    5. Appendix: the findings per evidence part, with reference problems

Read-only: the PDF carries the "no changes, no annotations" permission (printing and
copying text stay allowed). That stops normal PDF viewers from editing it, but it is
not tamper-proof; the SHA-256 of the PDF stored with the assessment proves whether a
copy was changed.
"""
from __future__ import annotations

import secrets
from collections import Counter
from io import BytesIO
from typing import List
from xml.sax.saxutils import escape

from services.assessment.data import Assessment, Reference
from services.branding import brand
from services.control_testing.data import CaseInterpretation

GREEN = "#1E7B34"
RED = "#B42318"
GREY = "#6B7280"
AMBER = "#B45309"
BLUE = "#1D4ED8"


def _duration(seconds: float) -> str:
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes} min {rest} s" if minutes else f"{rest} s"


def _ref(reference: Reference) -> str:
    return escape(reference.document + (f", {reference.location}" if reference.location else ""))


class AssessmentReport:
    def __init__(self, assessment: Assessment, interpretation: CaseInterpretation, case_name: str = "") -> None:
        self.assessment = assessment
        self.interpretation = interpretation
        self.case_name = case_name

    def build(self) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.pdfencrypt import StandardEncryption
        from reportlab.lib.units import cm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        from services.evidences.docx_converter import DocxConverter

        self.font = DocxConverter._register_font()
        self.brand = brand()
        self.styles = self._styles()
        self.colors, self.Table, self.TableStyle, self.Paragraph = colors, Table, TableStyle, Paragraph
        self.width = A4[0] - 4 * cm
        meta = self.assessment.metadata

        story = self._executive() + [PageBreak()] + self._header() + self._summary() + [PageBreak()]
        for verdict in self.assessment.verdicts:
            story += self._step(verdict)
        story += [PageBreak()] + self._evidence() + self._appendix()

        buffer = BytesIO()
        encryption = StandardEncryption("", ownerPassword=secrets.token_hex(16), canPrint=1, canModify=0,
                                        canCopy=1, canAnnotate=0)
        document = SimpleDocTemplate(
            buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.9 * cm, bottomMargin=2 * cm,
            title=f"Assessment {meta.case_reference} {meta.assessment_id}", author=f"{self.brand.name} KCT", encrypt=encryption,
        )
        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        return buffer.getvalue()

    # --- sections ----------------------------------------------------------------------

    def _executive(self) -> list:
        from services.assessment.matrix import Matrix, traceability

        meta = self.assessment.metadata
        verdicts = self.assessment.verdicts
        effective = sum(v.verdict == "effective" for v in verdicts)
        no_evidence = sum(v.no_evidence for v in verdicts)
        title = self.case_name or meta.case_reference
        story = [self.Paragraph("Control test assessment", self.styles["title"]),
                 self._p(title, "subtitle"), self._space(0.3)]

        kpis = [(str(effective), "effective", GREEN), (str(len(verdicts) - effective), "not effective", RED),
                (str(no_evidence), "without evidence", AMBER), (str(meta.evidence_files or len({p.unit for p in self.assessment.parts})),
                                                                 "evidence files", self.brand.navy)]
        cells = [[self.Paragraph(f"<font size=22 color='{color}'><b>{number}</b></font><br/>"
                                 f"<font size=8 color='{GREY}'>{escape(label)}</font>", self.styles["kpi"])
                  for number, label, color in kpis]]
        box = self.Table(cells, colWidths=[self.width / 4] * 4, rowHeights=[1.9 * 28.35])
        box.setStyle(self.TableStyle([("BOX", (0, 0), (-1, -1), 0.4, self.colors.HexColor("#D1D5DB")),
                                      ("INNERGRID", (0, 0), (-1, -1), 0.4, self.colors.HexColor("#D1D5DB")),
                                      ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [box, self._space(0.25)]

        facts = [f"{len(verdicts)} test steps", f"{meta.parts_total} evidence part(s) assessed"
                 + (f", {meta.parts_failed} failed" if meta.parts_failed else "")]
        if meta.duration_seconds is not None:
            facts.append(f"run time {_duration(meta.duration_seconds)}")
        if meta.input_tokens or meta.output_tokens:
            facts.append(f"{meta.input_tokens + meta.output_tokens:,} tokens")
        if meta.estimated_cost is not None:
            from services.config import settings

            facts.append(f"cost {meta.estimated_cost:.2f} {settings().price_currency}")
        facts.append(f"model {meta.model}")
        story += [self._p(" · ".join(facts), "muted"), self._space(0.35)]

        matrix = traceability(self.assessment)
        if matrix.units:
            story += [self.Paragraph("Traceability: what each evidence file shows per test step", self.styles["h2"])]
            header = [self._p("Step", "bold"), self._p("Verdict", "bold")] + \
                [self._p(Matrix.short(u), "matrixhead") for u in matrix.units]
            rows, style = [header], []
            symbols = {"supports": ("+", "#DCFCE7"), "contradicts": ("–", "#FEE2E2"), "partly": ("~", "#FEF3C7"),
                       "not_relevant": ("", "#FFFFFF"), "failed": ("?", "#E5E7EB")}
            for r_index, row in enumerate(matrix.rows, start=1):
                label = "EFFECTIVE" if row.verdict == "effective" else ("NO EVIDENCE" if row.no_evidence else "NOT EFFECTIVE")
                color = GREEN if row.verdict == "effective" else (AMBER if row.no_evidence else RED)
                line = [self._p(row.step_reference, "small_dark"),
                        self.Paragraph(f"<font color='{color}'><b>{label}</b></font>", self.styles["tiny"])]
                for c_index, unit in enumerate(matrix.units, start=2):
                    symbol, fill = symbols[row.cells[unit]]
                    line.append(self._p(symbol, "matrixcell"))
                    style.append(("BACKGROUND", (c_index, r_index), (c_index, r_index), self.colors.HexColor(fill)))
                rows.append(line)
            unit_width = min(2.2 * 28.35, (self.width - 2.4 * 28.35 - 3.0 * 28.35) / len(matrix.units))
            table = self.Table(rows, colWidths=[2.4 * 28.35, 3.0 * 28.35] + [unit_width] * len(matrix.units),
                               repeatRows=1)
            table.setStyle(self.TableStyle([("GRID", (0, 0), (-1, -1), 0.4, self.colors.HexColor("#D1D5DB")),
                                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                            ("BACKGROUND", (0, 0), (-1, 0), self.colors.HexColor(self.brand.orange_tint)),
                                            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                                            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)] + style))
            legend = "+ supports   – contradicts   ~ partly   (empty) not relevant   ? could not be assessed"
            columns = " · ".join(f"{Matrix.short(u)} = {u}" for u in matrix.units)
            story += [table, self._space(0.1), self._p(legend, "small"), self._p(columns, "small"), self._space(0.3)]

        exceptions = [(v.step_reference, e) for v in verdicts for e in v.exceptions]
        if exceptions:
            story.append(self.Paragraph("Key exceptions", self.styles["h2"]))
            for step, e in exceptions[:6]:
                where = f" ({_ref(e.reference)})" if e.reference else ""
                story.append(self._p(f"<b>{escape(e.item)}</b> · step {escape(step)}: {escape(e.description)}"
                                     f"<font color='{GREY}'>{where}</font>", escaped=True))
            if len(exceptions) > 6:
                story.append(self._p(f"… and {len(exceptions) - 6} more; see the test steps.", "muted"))
        return story

    def _header(self) -> list:
        meta = self.assessment.metadata
        interpretation = self.interpretation.metadata
        rows = [
            ("Case", meta.case_reference if self.case_name in ("", meta.case_reference)
             else f"{self.case_name} ({meta.case_reference})"),
            ("Assessment", meta.assessment_id),
            ("Test steps from", f"interpretation {interpretation.case_interpretation_id} ({interpretation.created_at[:19]})"),
            ("Model", f"{meta.provider} / {meta.model}"),
            ("Started", meta.created_at),
            ("Finished", meta.finished_at or "-"),
            ("Evidence parts", f"{meta.parts_total} ({meta.parts_done} assessed, {meta.parts_failed} failed)"),
        ]
        return [
            self.Paragraph("Control test assessment", self.styles["title"]),
            self._table([[self._p(k, "bold"), self._p(v)] for k, v in rows], [4.2, None], header=False),
            self._space(),
        ]

    def _summary(self) -> list:
        counts = Counter(v.verdict for v in self.assessment.verdicts)
        no_evidence = sum(v.no_evidence for v in self.assessment.verdicts)
        story = [self.Paragraph("Summary", self.styles["h1"]),
                 self._p(f"{counts['effective']} effective, {counts['not_effective']} not effective"
                         + (f" (of which {no_evidence} without any evidence)" if no_evidence else "")
                         + f", out of {len(self.assessment.verdicts)} test steps."),
                 self._space(0.2)]
        rows = [[self._p("Step", "bold"), self._p("Title", "bold"), self._p("Verdict", "bold"), self._p("Note", "bold")]]
        for v in self.assessment.verdicts:
            notes = (["no evidence"] if v.no_evidence else []) + (["fallback"] if v.fallback else []) \
                + ([f"{len(v.exceptions)} exception(s)"] if v.exceptions else [])
            rows.append([self._p(v.step_reference), self._p(v.title), self._verdict(v.verdict), self._p(", ".join(notes))])
        story.append(self._table(rows, [2.4, None, 3.0, 3.6]))
        if any(v.fallback for v in self.assessment.verdicts):
            story += [self._space(0.2), self._p("fallback: the model gave no verdict for the step, so it is set to not "
                                                "effective by the application.", "small")]
        return story

    def _step(self, verdict) -> list:
        step = next((s for s in self.interpretation.test_steps if s.id == verdict.test_step_id), None)
        story = [self.Paragraph(f"{escape(verdict.step_reference)}: {escape(verdict.title)}", self.styles["h2"]),
                 self._verdict(verdict.verdict, big=True)]
        if verdict.no_evidence:
            story.append(self._p("No evidence was found for this step.", "flag"))
        if step is not None:
            story += [self._p(step.description, "muted"), self._space(0.15),
                      self._p("Acceptance criteria", "bold"), *[self._p("• " + c) for c in step.acceptance_criteria],
                      self._p("Refusal criteria", "bold"), *[self._p("• " + c) for c in step.refusal_criteria]]
        story += [self._space(0.15), self._p("Reason", "bold"), self._p(verdict.reason)]
        if verdict.exceptions:
            rows = [[self._p("Item", "bold"), self._p("What fails", "bold"), self._p("Where", "bold")]]
            rows += [[self._p(e.item), self._p(e.description), self._p(_ref(e.reference) if e.reference else "-", escaped=True)]
                     for e in verdict.exceptions]
            story += [self._space(0.15), self._p("Exceptions", "bold"), self._table(rows, [3.0, None, 5.5])]
        if verdict.references:
            story += [self._space(0.15), self._p("Evidence", "bold"),
                      *[self._p("• " + _ref(r), escaped=True) for r in verdict.references]]
        if verdict.reference_problems:
            story += [self._space(0.1), *[self._p("Reference problem: " + p, "flag") for p in verdict.reference_problems]]
        return story + [self._space(0.5)]

    def _evidence(self) -> list:
        units = {}
        for part in self.assessment.parts:
            entry = units.setdefault(part.unit, {"sha": part.unit_sha256, "parts": 0, "failed": 0})
            entry["parts"] += 1
            entry["failed"] += part.status == "failed"
        rows = [[self._p("Evidence file", "bold"), self._p("SHA-256", "bold"), self._p("Parts", "bold")]]
        for unit, entry in units.items():
            parts = f"{entry['parts']}" + (f" ({entry['failed']} failed)" if entry["failed"] else "")
            rows.append([self._p(unit), self._p(entry["sha"], "mono"), self._p(parts)])
        story = [self.Paragraph("Evidence", self.styles["h1"])]
        if len(rows) == 1:
            return story + [self._p("No evidence files were uploaded for this case.")]
        return story + [self._p("The SHA-256 identifies the exact file assessed.", "small"), self._space(0.15),
                        self._table(rows, [6.0, None, 2.2]), self._space(0.4)]

    def _appendix(self) -> list:
        story = [self.Paragraph("Appendix: findings per evidence part", self.styles["h1"])]
        for part in self.assessment.parts:
            story.append(self.Paragraph(escape(part.label), self.styles["h3"]))
            if part.status == "failed":
                story += [self._p(f"Not assessed: {part.error}", "flag"), self._space(0.2)]
                continue
            rows = [[self._p("Step", "bold"), self._p("Relevance", "bold"), self._p("Summary", "bold")]]
            for f in part.findings:
                if f.relevance == "not_relevant" and not f.reference_problems:
                    continue
                summary = escape(f.summary) + "".join(
                    f"<br/><font color='{RED}'>Reference problem: {escape(p)}</font>" for p in f.reference_problems)
                rows.append([self._p(f.step_reference), self._p(f.relevance.replace("_", " ")),
                             self._p(summary, escaped=True)])
            if len(rows) == 1:
                story.append(self._p("Not relevant to any test step.", "muted"))
            else:
                story.append(self._table(rows, [2.4, 2.6, None]))
            story.append(self._space(0.2))
        return story

    # --- building blocks ----------------------------------------------------------------

    def _styles(self) -> dict:
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        base = getSampleStyleSheet()
        f, b = self.font, f"{self.font}-Bold"
        return {
            "title": ParagraphStyle("t", parent=base["Title"], fontName=b, fontSize=18, spaceAfter=12,
                                    textColor=self.brand.navy),
            "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=b, fontSize=14, spaceBefore=6,
                                 textColor=self.brand.navy),
            "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=b, fontSize=12, spaceBefore=4,
                                 textColor=self.brand.navy),
            "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=b, fontSize=10, textColor=self.brand.navy),
            "body": ParagraphStyle("b", parent=base["BodyText"], fontName=f, fontSize=9, leading=12),
            "bold": ParagraphStyle("bo", parent=base["BodyText"], fontName=b, fontSize=9, leading=12),
            "muted": ParagraphStyle("m", parent=base["BodyText"], fontName=f, fontSize=9, leading=12,
                                    textColor=GREY),
            "small": ParagraphStyle("s", parent=base["BodyText"], fontName=f, fontSize=8, leading=10,
                                    textColor=GREY),
            "mono": ParagraphStyle("mo", parent=base["BodyText"], fontName="Courier", fontSize=6.5, leading=8),
            "flag": ParagraphStyle("f", parent=base["BodyText"], fontName=b, fontSize=9, leading=12, textColor=RED),
            "verdict": ParagraphStyle("v", parent=base["BodyText"], fontName=b, fontSize=9, leading=12),
            "verdict_big": ParagraphStyle("vb", parent=base["BodyText"], fontName=b, fontSize=11, leading=15),
            "subtitle": ParagraphStyle("st", parent=base["BodyText"], fontName=f, fontSize=12, leading=15,
                                       alignment=1, textColor=GREY),
            "kpi": ParagraphStyle("k", parent=base["BodyText"], fontName=f, alignment=1, leading=24),
            "tiny": ParagraphStyle("ti", parent=base["BodyText"], fontName=f, fontSize=7, leading=8.5),
            "small_dark": ParagraphStyle("sd", parent=base["BodyText"], fontName=f, fontSize=8, leading=9.5),
            "matrixhead": ParagraphStyle("mh", parent=base["BodyText"], fontName=b, fontSize=7.5, leading=9,
                                         alignment=1),
            "matrixcell": ParagraphStyle("mc", parent=base["BodyText"], fontName=b, fontSize=10, leading=11,
                                         alignment=1),
        }

    def _p(self, text, style: str = "body", escaped: bool = False):
        return self.Paragraph(text if escaped else escape(str(text)), self.styles[style])

    def _verdict(self, verdict: str, big: bool = False):
        color = GREEN if verdict == "effective" else RED
        label = "EFFECTIVE" if verdict == "effective" else "NOT EFFECTIVE"
        return self.Paragraph(f"<font color='{color}'>{label}</font>", self.styles["verdict_big" if big else "verdict"])

    def _table(self, rows: List[list], widths: list, header: bool = True):
        from reportlab.lib.units import cm

        fixed = sum(w for w in widths if w) * cm
        free = max(1.0, (self.width - fixed) / max(1, sum(1 for w in widths if not w)))
        table = self.Table(rows, colWidths=[w * cm if w else free for w in widths], repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.4, self.colors.HexColor("#D1D5DB")),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), self.colors.HexColor(self.brand.orange_tint)))
        table.setStyle(self.TableStyle(style))
        return table

    @staticmethod
    def _space(height: float = 0.3):
        from reportlab.lib.units import cm
        from reportlab.platypus import Spacer

        return Spacer(1, height * cm)

    def _footer(self, canvas, document) -> None:
        from reportlab.lib.units import cm

        meta = self.assessment.metadata
        canvas.saveState()
        self._brand_header(canvas, document)
        canvas.setFont(self.font, 7)
        canvas.setFillColor(self.colors.HexColor(GREY))
        canvas.drawString(2 * cm, 1.2 * cm, f"KCT assessment {meta.assessment_id} · {meta.case_reference} · read-only")
        canvas.drawRightString(document.pagesize[0] - 2 * cm, 1.2 * cm, f"Page {document.page}")
        canvas.restoreState()

    def _brand_header(self, canvas, document) -> None:
        """Every page: the brand's logo (or wordmark) and the product name above an orange rule."""
        from reportlab.lib.units import cm

        width, height = document.pagesize
        top = height - 1.3 * cm
        canvas.setStrokeColor(self.colors.HexColor(self.brand.orange))
        canvas.setLineWidth(2)
        canvas.line(2 * cm, top - 0.35 * cm, width - 2 * cm, top - 0.35 * cm)
        if self.brand.logo:
            canvas.drawImage(str(self.brand.logo), 2 * cm, top - 0.2 * cm, height=0.75 * cm, width=2.6 * cm,
                             preserveAspectRatio=True, anchor="sw", mask="auto")
        else:
            canvas.setFont(f"{self.font}-Bold", 15)
            canvas.setFillColor(self.colors.HexColor(self.brand.orange))
            canvas.drawString(2 * cm, top, self.brand.name)
        canvas.setFont(self.font, 9)
        canvas.setFillColor(self.colors.HexColor(self.brand.navy))
        canvas.drawRightString(width - 2 * cm, top, f"{self.brand.product} · control test assessment")
