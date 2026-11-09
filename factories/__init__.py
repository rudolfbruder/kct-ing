"""Fake evidence files for demos and tests (Laravel: database/factories).

    from factories import DocxFactory, ExcelFactory, MsgFactory

    DocxFactory().create(folder)        Word document with a table and a screenshot
    ExcelFactory(rows=100).create(folder)  ING-style workbook: 4 sheets, colors, comments, hidden parts
    MsgFactory().create(folder)         Outlook email thread with Word, Excel, images and a forwarded email attached

make() returns the file as bytes instead of writing it.
"""
from factories.docx_factory import DocxFactory
from factories.excel_factory import ExcelFactory
from factories.msg_factory import MsgFactory

__all__ = ["DocxFactory", "ExcelFactory", "MsgFactory"]
