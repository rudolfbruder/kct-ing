"""Traceability matrix: which evidence file says what about which test step.

    matrix = traceability(assessment)
    matrix.cell("0472-04", "EV-01_password_reset_tickets_SAMPLE.docx")   -> "contradicts"

Rows are the test steps (with their verdict), columns the evidence files. A cell
combines every part of the file: contradicts > supports > partly > not_relevant;
"failed" when no part of the file could be assessed. It is the picture behind every
verdict: an effective step has green cells, a not effective step a red cell or none.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.assessment.data import Assessment

STRENGTH = {"contradicts": 4, "supports": 3, "partly": 2, "not_relevant": 1}


@dataclass
class MatrixRow:
    step_reference: str
    title: str
    verdict: str
    no_evidence: bool
    cells: Dict[str, str] = field(default_factory=dict)    # unit -> relevance or "failed"


@dataclass
class Matrix:
    units: List[str]
    rows: List[MatrixRow]

    def cell(self, step_reference: str, unit: str) -> Optional[str]:
        row = next((r for r in self.rows if r.step_reference == step_reference), None)
        return row.cells.get(unit) if row else None

    @staticmethod
    def short(unit: str) -> str:
        """A column label: the evidence ID (EV-01) when the name starts with one, else the file name."""
        name = unit.replace("\\", "/").rsplit("/", 1)[-1]
        match = re.match(r"([A-Za-z]{1,6}-\d{1,4})", name)
        return match.group(1) if match else (name if len(name) <= 18 else name[:16] + "…")


def traceability(assessment: Assessment) -> Matrix:
    units: List[str] = []
    for part in assessment.parts:
        if part.unit not in units:
            units.append(part.unit)
    units.sort(key=lambda u: (Matrix.short(u).lower(), u))
    best: Dict[tuple, str] = {}
    assessed = {u: False for u in units}
    for part in assessment.parts:
        if part.status != "assessed":
            continue
        assessed[part.unit] = True
        for finding in part.findings:
            key = (finding.step_reference, part.unit)
            if STRENGTH[finding.relevance] > STRENGTH.get(best.get(key, ""), 0):
                best[key] = finding.relevance
    rows = []
    for verdict in assessment.verdicts:
        cells = {u: (best.get((verdict.step_reference, u), "not_relevant") if assessed[u] else "failed") for u in units}
        rows.append(MatrixRow(verdict.step_reference, verdict.title, verdict.verdict, verdict.no_evidence, cells))
    return Matrix(units=units, rows=rows)
