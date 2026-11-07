"""EvidenceSplitter: cut an evidence unit into parts the model reads well.

Hard model limits (Gemini on Vertex: about 1,000-3,000 pages per PDF, 1M tokens of
context) are far above what works well: accuracy drops deep inside long documents,
and the answer for all test steps must fit the output limit. So a unit is split when

    a PDF has more than KCT_PDF_MAX_PAGES pages (default 50)
    a PDF is larger than KCT_PDF_MAX_MB (default 20; scans are big per page)
    a part would be estimated above KCT_EVIDENCE_MAX_TOKENS (default 300,000)

How:
    PDF     page ranges of max_pages with overlap_pages repeated at each cut (a table cut
            at a page break is still seen whole); a range still over max_mb is halved.
            Titles keep the real page numbers: "EV-07.pdf (pages 49-98 of 230)".
    Excel   text (.xlsx.md) by sheet; a sheet too big by row blocks, with the workbook
            heading and the table header repeated in every block; pictures go with
            their sheet.
    Email   the email text goes with every part; attachments are packed into parts.
    Other   text by lines; images are never split.

Small pieces are packed together, so a unit that fits is one part.
"""
from __future__ import annotations

import io
import re
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Optional, Tuple

from services.ai.attachments import Document
from services.evidences.units import EvidenceUnit

# Rough token costs for estimates (Gemini: ~258-560 tokens per PDF page, more for images).
PDF_PAGE_TOKENS = 560
IMAGE_TOKENS = 1100
CHARS_PER_TOKEN = 4


@dataclass
class EvidencePart:
    unit: str                    # the unit's path, relative to the case's evidence folder
    number: int
    total: int
    documents: List[Document]
    estimated_tokens: int

    @property
    def label(self) -> str:
        return self.unit if self.total == 1 else f"{self.unit} (part {self.number} of {self.total})"


class EvidenceSplitter:
    def __init__(self, max_pages: int = 50, max_mb: float = 20, overlap_pages: int = 2,
                 max_tokens: int = 300_000) -> None:
        if max_pages < 1 or max_tokens < 1000:
            raise ValueError("max_pages must be >= 1 and max_tokens >= 1000")
        self.max_pages = max_pages
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.overlap = max(0, min(overlap_pages, max_pages - 1))
        self.max_tokens = max_tokens

    @classmethod
    def from_settings(cls, config) -> "EvidenceSplitter":
        return cls(config.pdf_max_pages, config.pdf_max_mb, config.pdf_overlap_pages, config.evidence_max_tokens)

    # --- public --------------------------------------------------------------------

    def split(self, unit: EvidenceUnit) -> List[EvidencePart]:
        anchor_tokens = self.tokens(unit.anchor) if unit.anchor else 0
        budget = max(1000, self.max_tokens - anchor_tokens)

        chunks: List[List[Document]] = []
        for group in unit.groups:
            chunks.extend(self._split_group(group, budget))

        parts: List[List[Document]] = []
        current: List[Document] = []
        for chunk in chunks:
            if current and not self._fits(current + chunk, budget):
                parts.append(current)
                current = []
            current = current + chunk
        if current or not parts:
            parts.append(current)

        total = len(parts)
        return [
            EvidencePart(
                unit=str(unit.path), number=number, total=total,
                documents=([unit.anchor] if unit.anchor else []) + docs,
                estimated_tokens=anchor_tokens + sum(self.tokens(d) for d in docs),
            )
            for number, docs in enumerate(parts, start=1)
        ]

    @staticmethod
    def tokens(doc: Document) -> int:
        if doc.mime_type == "application/pdf":
            return _page_count(doc.data) * PDF_PAGE_TOKENS
        if doc.is_image:
            return IMAGE_TOKENS
        return len(doc.data.decode("utf-8", errors="replace")) // CHARS_PER_TOKEN + 1

    # --- groups ----------------------------------------------------------------------

    def _fits(self, docs: List[Document], budget: int) -> bool:
        pages = sum(_page_count(d.data) for d in docs if d.mime_type == "application/pdf")
        size = sum(len(d.data) for d in docs)
        return (sum(self.tokens(d) for d in docs) <= budget and pages <= self.max_pages
                and size <= self.max_bytes)

    def _split_group(self, group: List[Document], budget: int) -> List[List[Document]]:
        if self._fits(group, budget):
            return [group]
        texts = [d for d in group if d.is_text]
        images = [d for d in group if d.is_image]
        pdfs = [d for d in group if d.mime_type == "application/pdf"]
        chunks: List[List[Document]] = []
        for text in texts:
            if text.title.lower().endswith((".xlsx.md", ".xlsm.md")):
                chunks.extend(self._split_workbook(text, images, budget))
                images = []  # placed with their sheets
            else:
                chunks.extend([[d] for d in self._split_text(text, budget)])
        for pdf in pdfs:
            chunks.extend([[d] for d in self._split_pdf(pdf)])
        chunks.extend([[image] for image in images])
        return chunks

    # --- PDF -------------------------------------------------------------------------

    def _split_pdf(self, doc: Document) -> List[Document]:
        pages = _page_count(doc.data)
        if pages <= self.max_pages and len(doc.data) <= self.max_bytes:
            return [doc]
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(doc.data))
        ranges: List[Tuple[int, int]] = []
        start = 0
        while start < pages:
            end = min(start + self.max_pages, pages)
            ranges.append((start, end))
            if end == pages:
                break
            start = end - self.overlap
        out: List[Document] = []
        for first, last in ranges:
            out.extend(self._pdf_range(reader, doc.title, first, last, pages))
        return out

    def _pdf_range(self, reader, title: str, first: int, last: int, pages: int) -> List[Document]:
        from pypdf import PdfWriter

        writer = PdfWriter()
        for index in range(first, last):
            writer.add_page(reader.pages[index])
        buffer = io.BytesIO()
        writer.write(buffer)
        data = buffer.getvalue()
        if len(data) > self.max_bytes and last - first > 1:
            middle = (first + last) // 2
            return self._pdf_range(reader, title, first, middle, pages) + \
                self._pdf_range(reader, title, middle, last, pages)
        pages_label = f"page {first + 1}" if last - first == 1 else f"pages {first + 1}-{last}"
        return [Document(data=data, title=f"{title} ({pages_label} of {pages})", mime_type="application/pdf")]

    # --- text ------------------------------------------------------------------------

    def _split_text(self, doc: Document, budget: int, keep: Optional[List[str]] = None,
                    label: str = "lines") -> List[Document]:
        """Lines packed into blocks under the budget; `keep` lines start every block."""
        lines = doc.data.decode("utf-8", errors="replace").split("\n")
        keep = keep or []
        limit = budget * CHARS_PER_TOKEN - sum(len(k) + 1 for k in keep)
        blocks: List[Tuple[int, int]] = []
        start, size = 0, 0
        for index, line in enumerate(lines):
            if size and size + len(line) + 1 > limit:
                blocks.append((start, index))
                start, size = index, 0
            size += len(line) + 1
        blocks.append((start, len(lines)))
        if len(blocks) == 1 and not keep:
            return [doc]
        return [
            Document(data="\n".join(keep + lines[a:b]).encode("utf-8"),
                     title=f"{doc.title} ({label} {a + 1}-{b} of {len(lines)})", mime_type=doc.mime_type)
            for a, b in blocks
        ]

    def _split_workbook(self, doc: Document, images: List[Document], budget: int) -> List[List[Document]]:
        """Workbook text by sheet, big sheets by row blocks; pictures follow their sheet."""
        text = doc.data.decode("utf-8", errors="replace")
        pieces = re.split(r"(?m)^(?=## Sheet \d+ of \d+)", text)
        preamble, sheets = pieces[0], pieces[1:]
        heading = [line for line in preamble.rstrip().split("\n")]
        chunks: List[List[Document]] = []
        for sheet in sheets:
            number = int(re.match(r"## Sheet (\d+)", sheet).group(1))
            sheet_images = [i for i in images if re.search(rf"(^|/)sheet{number}_image", i.title)]
            sheet_title = sheet.split("\n", 1)[0].lstrip("# ").strip()
            sheet_doc = Document(data=("\n".join(heading) + "\n\n" + sheet).encode("utf-8"),
                                 title=f"{doc.title} ({sheet_title})", mime_type=doc.mime_type)
            if self._fits([sheet_doc] + sheet_images, budget):
                chunks.append([sheet_doc] + sheet_images)
                continue
            # Too big: row blocks with the workbook heading and the table header in each.
            lines = sheet.split("\n")
            table = next((i for i, line in enumerate(lines) if line.startswith("|---")), 1)
            keep = heading + [""] + lines[:table + 1]
            rows = Document(data="\n".join(lines[table + 1:]).encode("utf-8"),
                            title=f"{doc.title} ({sheet_title})", mime_type=doc.mime_type)
            blocks = self._split_text(rows, budget - IMAGE_TOKENS * len(sheet_images), keep=keep,
                                      label="table lines")
            chunks.append([blocks[0]] + sheet_images)
            chunks.extend([[b] for b in blocks[1:]])
        if not sheets:
            chunks.extend([[d] for d in self._split_text(doc, budget)])
        return chunks


@lru_cache(maxsize=512)
def _page_count(data: bytes) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        # Without pypdf (or for a damaged file) guess from the page objects in the bytes.
        return max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))
