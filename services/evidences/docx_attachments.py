"""Files embedded in a Word document (.docx): attached files, embedded workbooks, documents.

    for attachment in embedded_files(Path("EV-01.docx")):
        attachment.name      # "Budget 2026.xlsx"
        attachment.data      # the file's bytes

Word keeps embedded files in word/embeddings/ of the .docx (a ZIP), in two forms:

    package      a whole Office file, e.g. Microsoft_Excel_Worksheet.xlsx or
                 Microsoft_Word_Document.docx (what Insert > Object > Excel does)
    OLE object   oleObject1.bin, an OLE compound file. What is inside depends on
                 how it was embedded:
                   "\\x01Ole10Native" stream   any file dropped into Word (a PDF, a .msg,
                                              a .zip ...): holds the original name and bytes
                   "Package" stream           an Office file (.docx, .xlsx, .pptx)
                   "CONTENTS" stream          often a PDF (Acrobat)
                   "Workbook" / "WordDocument" an old Excel (.xls) / Word (.doc) file: the
                                              .bin itself is that file
                 Anything else is kept as .bin.

The order is the order in which the objects appear in the document. Needs no package: OLE
files are read with services/evidences/ole.py.
"""
from __future__ import annotations

import io
import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Optional
from xml.etree import ElementTree

from services.evidences.ole import OleError, is_ole, ole_streams

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
EMBED_TYPES = ("/oleObject", "/package")   # relationship types that point at embedded files
MAX_FILES = 200                              # a document with more embedded files is not normal


@dataclass(frozen=True)
class EmbeddedFile:
    name: str          # the original file name when Word kept it, else a name from the type
    data: bytes
    part: str          # where it is inside the .docx, e.g. word/embeddings/oleObject1.bin
    kind: str          # "package", "ole-native", "ole-package", "ole-contents", "ole-file", "ole-unknown"

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name).suffix.lower()


def embedded_files(source: Path) -> List[EmbeddedFile]:
    """Every file embedded in the .docx, in document order. Empty list when there are none."""
    with zipfile.ZipFile(source) as package:
        names = set(package.namelist())
        parts = _ordered_parts(package, names)
        files = []
        for part in parts[:MAX_FILES]:
            files.append(_read(part, package.read(part)))
    return files


# --- which parts, in which order -----------------------------------------------------------

def _ordered_parts(package: zipfile.ZipFile, names: set) -> List[str]:
    """Embedded parts referenced by the main document (in the order their ids appear), then any
    other file under word/embeddings/ (headers, footers, or not referenced at all)."""
    ordered: List[str] = []
    rels_name = "word/_rels/document.xml.rels"
    if rels_name in names and "word/document.xml" in names:
        targets = {}
        root = ElementTree.fromstring(package.read(rels_name))
        for rel in root.findall(f"{{{REL_NS}}}Relationship"):
            if rel.get("TargetMode") == "External":
                continue
            if any(rel.get("Type", "").endswith(t) for t in EMBED_TYPES):
                target = str(PurePosixPath("word") / rel.get("Target", ""))
                targets[rel.get("Id")] = _normalize(target)
        document = package.read("word/document.xml").decode("utf-8", errors="replace")
        for rel_id in re.findall(r'r:id="([^"]+)"', document):
            part = targets.get(rel_id)
            if part and part in names and part not in ordered:
                ordered.append(part)
    for name in sorted(names):
        if name.startswith("word/embeddings/") and not name.endswith("/") and name not in ordered:
            ordered.append(name)
    return ordered


def _normalize(path: str) -> str:
    """word/../word/embeddings/x -> word/embeddings/x"""
    out: List[str] = []
    for piece in path.split("/"):
        if piece == "..":
            if out:
                out.pop()
        elif piece and piece != ".":
            out.append(piece)
    return "/".join(out)


# --- what is inside each part --------------------------------------------------------------

def _read(part: str, data: bytes) -> EmbeddedFile:
    base = PurePosixPath(part).name
    if not is_ole(data):                     # not an OLE file: a package (.xlsx, .docx ...)
        return EmbeddedFile(name=_with_office_suffix(base, data), data=data, part=part, kind="package")
    try:
        streams = ole_streams(data)
    except (OleError, struct.error, UnicodeDecodeError):
        return EmbeddedFile(name=base, data=data, part=part, kind="ole-unknown")
    stem = PurePosixPath(base).stem
    if "\x01ole10native" in streams:
        native = parse_ole10native(streams["\x01ole10native"])
        if native:
            name, content = native
            return EmbeddedFile(name=name, data=content, part=part, kind="ole-native")
    if "package" in streams:
        content = streams["package"]
        return EmbeddedFile(name=_with_office_suffix(stem, content), data=content, part=part, kind="ole-package")
    if "contents" in streams:
        content = streams["contents"]
        suffix = ".pdf" if content.startswith(b"%PDF") else ".bin"
        return EmbeddedFile(name=stem + suffix, data=content, part=part, kind="ole-contents")
    if "workbook" in streams or "book" in streams:
        return EmbeddedFile(name=stem + ".xls", data=data, part=part, kind="ole-file")
    if "worddocument" in streams:
        return EmbeddedFile(name=stem + ".doc", data=data, part=part, kind="ole-file")
    if "powerpoint document" in streams:
        return EmbeddedFile(name=stem + ".ppt", data=data, part=part, kind="ole-file")
    if "__properties_version1.0" in streams:
        return EmbeddedFile(name=stem + ".msg", data=data, part=part, kind="ole-file")
    return EmbeddedFile(name=base, data=data, part=part, kind="ole-unknown")


def _with_office_suffix(name: str, data: bytes) -> str:
    """Give a ZIP-based Office file the right suffix, judged by what is inside it."""
    suffix = _office_suffix(data)
    if not suffix:
        return name
    stem = PurePosixPath(name).stem if PurePosixPath(name).suffix else name
    return stem + suffix


def _office_suffix(data: bytes) -> Optional[str]:
    if not data.startswith(b"PK"):
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            names = set(inner.namelist())
    except zipfile.BadZipFile:
        return None
    if "word/document.xml" in names:
        return ".docx"
    if "xl/workbook.xml" in names:
        return ".xlsm" if "xl/vbaProject.bin" in names else ".xlsx"
    if "ppt/presentation.xml" in names:
        return ".pptx"
    return ".zip"


# --- the Ole10Native stream ----------------------------------------------------------------
#
#   uint32 total size | uint16 type (2) | label\0 | original path\0 | uint32 (0x00030000)
#   | uint32 temp path length | temp path\0 | uint32 data size | data | (optional unicode names)

def parse_ole10native(stream: bytes):
    """(file name, bytes) from an Ole10Native stream, or None when it is not readable."""
    try:
        pos = 6
        label, pos = _cstring(stream, pos)
        original, pos = _cstring(stream, pos)
        pos += 4
        (temp_len,) = struct.unpack_from("<I", stream, pos)
        pos += 4
        temp = stream[pos:pos + temp_len].split(b"\0", 1)[0].decode("latin-1")
        pos += temp_len
        (size,) = struct.unpack_from("<I", stream, pos)
        pos += 4
        if size > len(stream) - pos:
            return None
        data = stream[pos:pos + size]
    except (struct.error, ValueError):
        return None
    name = next((PurePosixPath(n.replace("\\", "/")).name for n in (label, original, temp) if n.strip()), "")
    return (name or "attachment.bin"), data


def make_ole10native(name: str, data: bytes) -> bytes:
    """The reverse of parse_ole10native; used to build fake documents for tests."""
    label = name.encode("latin-1", errors="replace") + b"\0"
    path = ("C:\\Users\\fake\\" + name).encode("latin-1", errors="replace") + b"\0"
    temp = ("C:\\Temp\\" + name).encode("latin-1", errors="replace") + b"\0"
    body = (struct.pack("<H", 2) + label + path + struct.pack("<I", 0x00030000)
            + struct.pack("<I", len(temp)) + temp + struct.pack("<I", len(data)) + data)
    return struct.pack("<I", len(body)) + body


def _cstring(data: bytes, pos: int):
    end = data.index(b"\0", pos)
    return data[pos:end].decode("latin-1"), end + 1
