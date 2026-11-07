"""Write the fake evidence files into the evidences folder.

    python scripts/make_sample_evidence.py

Uses the factories in factories/ (made-up data for the sample case PRC-IAM-014):

    EV-01_..._SAMPLE.docx   DocxFactory: Word with headings, a list, a table and a screenshot
    EV-03_..._SAMPLE.xlsx   ExcelFactory: ING-style workbook, 4 sheets, 20 columns x 100 rows,
                            colors, comments, hidden parts, formulas, a pasted screenshot
    EV-04_..._SAMPLE.msg    MsgFactory: Outlook email with the Word and Excel files, an inline
                            screenshot and a forwarded approval email attached
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factories import DocxFactory, ExcelFactory, MsgFactory  # noqa: E402
from services.config import settings  # noqa: E402

if __name__ == "__main__":
    folder = settings().evidences_root
    for factory in (DocxFactory(), ExcelFactory(), MsgFactory()):
        print(factory.create(folder))
