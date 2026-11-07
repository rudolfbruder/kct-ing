"""ExcelFactory: a fake ING-style evidence workbook (Laravel: a model factory).

    ExcelFactory().create(folder)          writes EV-03_..._SAMPLE.xlsx into folder, returns the path
    ExcelFactory(rows=15).make()           the .xlsx as bytes (for example as an email attachment)

What real evidence workbooks tend to contain, with made-up data:
4 sheets (one hidden); a 20-column table with `rows` rows, a merged title, a
colored header, light red exception rows with red text, reviewer comments, a
yellow "to check" cell, a hidden column; a two-level merged header with a
hidden row; a form-style summary with formulas, conditional formatting and a
pasted screenshot. Needs openpyxl and Pillow.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from factories.images import audit_log_screenshot

AGENTS = ["AGT-0193", "AGT-0207", "AGT-0211", "AGT-0222", "AGT-0230"]
SYSTEMS = ["ADX", "SAP-HR", "Mainframe", "Citrix", "Exchange"]
REGIONS = ["NL", "BE", "DE", "PL", "RO"]


def _reset_rows(count: int):
    """Made-up reset events. Rows 7 and 12 (and every 15th) are exceptions."""
    import random
    from datetime import datetime, timedelta

    random.seed(14)
    rows = []
    start = datetime(2026, 1, 5, 8, 0)
    for n in range(count):
        verified = start + timedelta(days=n * 3, minutes=random.randint(0, 480))
        exception = n in (6, 11) or (n > 0 and n % 15 == 0)
        executed = verified + timedelta(minutes=(-1 if exception else random.randint(1, 9)))
        verifier = random.choice(AGENTS)
        executor = random.choice([a for a in AGENTS if a != verifier]) if exception else verifier
        rows.append({
            "exception": exception,
            "values": [
                f"EVT-{90000 + n}", f"SD-{104200 + n * 37}", random.choice(SYSTEMS), "RESET_PASSWORD",
                f"adm_{random.choice(['jdoe', 'kvan', 'mpol', 'abak'])}", "Privileged",
                verified, executed, verifier, executor,
                random.choice(["Callback + employee ID", "Callback + manager confirmation", "Employee ID only"]),
                random.choice(REGIONS),
                f"10.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
                random.choice(["Phone", "Phone", "Walk-in"]), random.choice(["P2", "P3"]),
                random.randint(1, 30), round(random.uniform(0.5, 1.0), 2),
                "No" if exception else "Yes", f"internal-{n}", "",
            ],
        })
    return rows


class ExcelFactory:
    name = "EV-03_ADX_audit_log_extract_SAMPLE.xlsx"

    def __init__(self, rows: int = 100) -> None:
        self.rows = rows

    def make(self) -> bytes:
        rows = self.rows
        from openpyxl import Workbook
        from openpyxl.comments import Comment
        from openpyxl.drawing.image import Image as XlImage
        from openpyxl.formatting.rule import CellIsRule
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        blue = PatternFill("solid", fgColor="1F4E78")
        light_red = PatternFill("solid", fgColor="FFC7CE")
        yellow = PatternFill("solid", fgColor="FFFF00")
        green = PatternFill("solid", fgColor="C6EFCE")
        grey = PatternFill("solid", fgColor="D9D9D9")
        white_bold = Font(bold=True, color="FFFFFF")

        wb = Workbook()

        # Sheet 1: wide event table, 20 columns.
        ws = wb.active
        ws.title = "Reset events"
        headers = [
            "Event ID", "Ticket", "System", "Action", "Target account", "Account type", "Verified at",
            "Executed at", "Verified by", "Executed by", "Verification factors", "Region", "Source IP",
            "Channel", "Priority", "Handling min", "Confidence", "Same agent", "Internal ref", "Reviewer remark",
        ]
        last = get_column_letter(len(headers))
        ws["A1"] = "ADX audit log extract: password resets of privileged accounts, 2026 Q1 (SAMPLE, made-up data)"
        ws["A1"].font = Font(bold=True, size=14)
        ws.merge_cells(f"A1:{last}1")
        ws["A2"] = "Exported 2026-03-31 by IAM Operations. Red rows: exception found by the reviewer."
        ws.merge_cells(f"A2:{last}2")
        for column, header in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=column, value=header)
            cell.fill, cell.font = blue, white_bold
            cell.alignment = Alignment(wrap_text=True)
        for index, row in enumerate(_reset_rows(rows), start=4):
            for column, value in enumerate(row["values"], start=1):
                cell = ws.cell(row=index, column=column, value=value)
                if column in (7, 8):
                    cell.number_format = "yyyy-mm-dd hh:mm"
                if column == 17:
                    cell.number_format = "0%"
                if row["exception"]:
                    cell.fill = light_red
            if row["exception"]:
                ws.cell(row=index, column=10).font = Font(color="FF0000", bold=True)
                ws.cell(row=index, column=20, value="Executed before verification by another agent")
                ws.cell(row=index, column=8).comment = Comment("Timestamp earlier than verification.", "Reviewer")
        ws.cell(row=8, column=11).fill = yellow
        ws.cell(row=8, column=11).comment = Comment("Only one factor? Check with service desk.", "Reviewer")
        ws.column_dimensions["S"].hidden = True  # internal reference, hidden in the export
        ws.freeze_panes = "C4"
        for column in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(column)].width = 16

        # Sheet 2: two-level header (group headers merged over their columns).
        ws2 = wb.create_sheet("User master")
        groups = [("Identity", 4), ("Access", 6), ("Review", 4)]
        sub = ["User ID", "Name", "Department", "Manager", "Account", "Type", "Granted", "Expires",
               "Approver", "MFA", "Last review", "Reviewer", "Result", "Remark"]
        column = 1
        for name, width in groups:
            ws2.cell(row=1, column=column, value=name).fill = grey
            ws2.merge_cells(start_row=1, start_column=column, end_row=1, end_column=column + width - 1)
            column += width
        for column, header in enumerate(sub, start=1):
            ws2.cell(row=2, column=column, value=header).font = Font(bold=True)
        from datetime import date
        for n in range(20):
            result = "Revoke" if n in (4, 13) else "Keep"
            values = [f"u{20000 + n}", f"Employee {n + 1}", ["IT Ops", "Finance", "HR", "Risk"][n % 4],
                      f"Manager {n % 5 + 1}", f"adm_{n:03d}", "Privileged" if n % 3 == 0 else "Standard",
                      date(2025, 1 + n % 12, 1), date(2026, 12, 31), AGENTS[n % 5], "Yes" if n % 7 else "No",
                      date(2026, 2, 1 + n % 27), "Reviewer A", result, "Left the team" if result == "Revoke" else ""]
            for column, value in enumerate(values, start=1):
                cell = ws2.cell(row=n + 3, column=column, value=value)
            ws2.cell(row=n + 3, column=13).fill = light_red if result == "Revoke" else green
        ws2.row_dimensions[10].hidden = True  # a row someone hid

        # Sheet 3: form layout, formulas, conditional formatting, a pasted screenshot.
        ws3 = wb.create_sheet("Summary")
        form = [
            ("Control", "CTL-IAM-0472"),
            ("Population", f"=COUNTA('Reset events'!A4:A{rows + 3})"),
            ("Exceptions", "=COUNTIF('Reset events'!R4:R{0},\"No\")".format(rows + 3)),
            ("Exception rate", "=B3/B2"),
            ("Conclusion", "Not effective: executions before verification"),
            ("Prepared by", "IAM Operations"),
            ("Reviewed by", "Reviewer A"),
        ]
        ws3["A1"] = "Test summary"
        ws3["A1"].font = Font(bold=True, size=13)
        for row, (label, value) in enumerate(form, start=2):
            ws3.cell(row=row, column=1, value=label).font = Font(bold=True)
            ws3.cell(row=row, column=2, value=value)
        ws3["B5"].number_format = "0.0%"
        ws3.conditional_formatting.add("B4", CellIsRule(operator="greaterThan", formula=["0"], fill=light_red))
        ws3["B6"].font = Font(color="C00000", bold=True)
        picture = XlImage(audit_log_screenshot())
        picture.width, picture.height = 630, 182
        ws3.add_image(picture, "D2")

        # Sheet 4: hidden lookup list.
        ws4 = wb.create_sheet("Lookup")
        for row, agent in enumerate(AGENTS, start=1):
            ws4.cell(row=row, column=1, value=agent)
            ws4.cell(row=row, column=2, value=f"Service desk agent {row}")
        ws4.sheet_state = "hidden"


        buffer = BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    def create(self, target: Union[str, Path]) -> Path:
        """Write the workbook. target is a folder (the default name is used) or a file path."""
        path = Path(target)
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            path = path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.make())
        return path
