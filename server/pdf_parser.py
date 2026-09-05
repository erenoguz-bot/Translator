"""PDF parsing: layout-aware text extraction with PyMuPDF.

Produces a structured document model:
  - document metadata (title, author, page size, TOC, image count)
  - per-page info (size, text presence, word count)
  - paragraphs with font styling (size ratio, bold/italic), alignment,
    page and position — enough to reconstruct a styled PDF afterwards.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

from .config import OCR_DPI
from .ocr import OCREngine, OCRLine, get_ocr

MEDIAN_SIZE = 10.0


@dataclass
class Paragraph:
    text: str
    page: int                  # 0-based
    y: float                   # vertical position of first line (page coords)
    size: float                # font size (pt)
    bold: bool = False
    italic: bool = False
    align: str = "left"        # left | center | right
    kind: str = "body"         # title | heading | body | list | table | caption
    style_ratio: float = 1.0   # size relative to body median
    x0: float = 0.0
    x1: float = 0.0
    source: str = "text"       # text | ocr
    y_end: float = 0.0         # bottom of last line

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "page": self.page,
            "size": round(self.size, 2),
            "bold": self.bold,
            "italic": self.italic,
            "align": self.align,
            "kind": self.kind,
            "source": self.source,
        }


@dataclass
class PageInfo:
    number: int                # 1-based
    width: float
    height: float
    has_text: bool
    words: int = 0


@dataclass
class ParsedDocument:
    id: str
    filename: str
    path: Path
    title: str
    author: str
    pages: list[PageInfo] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)
    toc: list[dict] = field(default_factory=list)
    image_count: int = 0
    page_size: tuple[float, float] = (595.0, 842.0)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def word_count(self) -> int:
        return sum(p.word_count for p in self.paragraphs)

    def text(self, pages: list[int] | None = None) -> str:
        return "\n".join(
            p.text for p in self.paragraphs
            if pages is None or (p.page + 1) in pages
        )

    def summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "author": self.author,
            "pages": self.page_count,
            "page_size": list(self.page_size),
            "image_count": self.image_count,
            "word_count": sum(p.word_count for p in self.paragraphs),
            "paragraph_count": len(self.paragraphs),
            "toc": self.toc,
            "page_info": [
                {
                    "number": p.number,
                    "width": p.width,
                    "height": p.height,
                    "has_text": p.has_text,
                    "words": p.words,
                }
                for p in self.pages
            ],
            "scanned_pages": [p.number for p in self.pages if not p.has_text],
            "paragraphs": [p.to_dict() for p in self.paragraphs],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _align_of(bbox, page_width: float) -> str:
    x0, _y0, x1, _y1 = bbox
    width = max(x1 - x0, 1e-3)
    left = x0
    right = page_width - x1
    if width > page_width * 0.7:      # full-width line: left or right only
        return "right" if right < left - 12 else "left"
    if abs(left - right) < max(10, width * 0.15):
        return "center"
    if right < left - max(15, width * 0.3):
        return "right"
    return "left"


def _clean(text: str) -> str:
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _group_lines_to_paragraphs(lines: list[dict], page: int, page_width: float,
                               size_median: float) -> list[Paragraph]:
    """Group extracted lines into paragraphs by vertical gap + style change."""
    out: list[Paragraph] = []
    buf: list[dict] = []
    prev: dict | None = None

    def flush():
        nonlocal buf
        if not buf:
            return
        text = _clean(" ".join(l["text"] for l in buf))
        if text:
            out.append(_make_paragraph(text, buf[0], buf[-1], page,
                                       page_width, size_median))
        buf = []

    for ln in lines:
        if prev is not None:
            gap = ln["y0"] - prev["y1"]
            lh = max(prev["y1"] - prev["y0"], 1.0)
            same_style = abs(ln["size"] - prev["size"]) < 0.75 and ln["bold"] == prev["bold"]
            if gap > lh * 1.55 and same_style:
                flush()
        buf.append(ln)
        prev = ln
    flush()
    return out


def _make_paragraph(text: str, rep: dict, last: dict, page: int,
                    page_width: float, size_median: float) -> Paragraph:
    size = rep["size"]
    ratio = size / size_median if size_median > 0 else 1.0
    if ratio >= 1.7 and rep["y"] < 120:
        kind = "title"
    elif ratio >= 1.3 or (ratio >= 1.15 and rep["bold"]):
        kind = "heading"
    elif re.match(r"^\s*(?:[-•▪◦‣·]|\d{1,2}[.)])\s+", text):
        kind = "list"
    elif size < size_median * 0.85 and len(text) < 90:
        kind = "caption"
    else:
        kind = "body"
    return Paragraph(
        text=text,
        page=page,
        y=rep["y"],
        size=size,
        bold=rep["bold"],
        italic=rep.get("italic", False),
        align=rep.get("align", "left"),
        kind=kind,
        style_ratio=ratio,
        x0=rep["x0"],
        x1=rep["x1"],
        y_end=last["y1"],
    )


def _merge_continuations(paras: list[Paragraph]) -> list[Paragraph]:
    """Merge paragraphs that are clearly one sentence/paragraph split across
    adjacent PDF blocks (same page, same style, normal line gap)."""
    out: list[Paragraph] = []
    for p in paras:
        if out:
            prev = out[-1]
            gap = p.y - prev.y_end
            if (
                prev.page == p.page
                and prev.kind == p.kind
                and prev.kind in ("body", "list")
                and abs(prev.size - p.size) < 0.5
                and prev.bold == p.bold
                and gap < max(1.0, prev.size * 1.2)
                and gap > -2.0
            ):
                prev.text = _clean(f"{prev.text} {p.text}")
                prev.y_end = p.y_end
                continue
        out.append(p)
    return out


_NUM_LIST = re.compile(r"^\s*(\d{1,2})\s+\S")


def _mark_numbered_lists(paras: list[Paragraph]) -> list[Paragraph]:
    """Detect consecutive '1 … 2 … 3 …' items as list paragraphs."""
    i = 0
    while i < len(paras):
        p = paras[i]
        if p.kind == "body":
            m = _NUM_LIST.match(p.text)
            if m:
                seq = [int(m.group(1))]
                j = i + 1
                while (j < len(paras) and paras[j].kind == "body"
                       and paras[j].page == p.page):
                    mj = _NUM_LIST.match(paras[j].text)
                    if mj and int(mj.group(1)) == seq[-1] + 1:
                        seq.append(int(mj.group(1)))
                        j += 1
                    else:
                        break
                if len(seq) >= 2:
                    for k in range(i, j):
                        paras[k].kind = "list"
                    i = j
                    continue
        i += 1
    return paras


def _line_dict(line: dict, page_width: float) -> dict | None:
    text = ""
    size = 0.0
    bold = False
    italic = False
    for span in line.get("spans", []):
        t = span.get("text", "")
        if not t:
            continue
        text += t
        size += span.get("size", 0) * len(t)
        bold = bold or bool(span.get("flags", 0) & 2**4)
        italic = italic or bool(span.get("flags", 0) & 2**1)
    text = text.strip()
    if not text:
        return None
    chars = max(len(text), 1)
    x0, y0, x1, y1 = line.get("bbox", (0, 0, 0, 0))
    return {
        "text": text,
        "y": y0,
        "y0": y0,
        "y1": y1,
        "x0": x0,
        "x1": x1,
        "size": size / chars if size else 10.0,
        "bold": bold,
        "italic": italic,
        "align": _align_of((x0, y0, x1, y1), page_width),
    }


def _page_blocks(page_dict: dict) -> list[list[dict]]:
    """Extract lines, grouped by text block (a PDF block ≈ a paragraph unit)."""
    page_width = page_dict.get("width", 612)
    blocks: list[list[dict]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # text blocks only
            continue
        lines: list[dict] = []
        for line in block.get("lines", []):
            ld = _line_dict(line, page_width)
            if ld:
                lines.append(ld)
        if lines:
            lines.sort(key=lambda l: (l["y"], l["x0"]))
            blocks.append(lines)
    return blocks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_pdf(path: Path, doc_id: str | None = None) -> ParsedDocument:
    path = Path(path)
    doc_id = doc_id or uuid.uuid4().hex[:12]
    doc = fitz.open(str(path))

    if doc.needs_pass:
        doc.close()
        raise ValueError("PDF is password-protected and cannot be opened.")

    meta = doc.metadata or {}
    page_size = (doc[0].rect.width, doc[0].rect.height) if doc.page_count else (595, 842)
    toc = doc.get_toc() or []
    toc_out = [
        {"level": t[0], "title": t[1], "page": t[2]} for t in toc[:200]
    ]

    image_count = 0
    pages: list[PageInfo] = []
    paragraphs: list[Paragraph] = []

    for pno in range(doc.page_count):
        page = doc[pno]
        p_dict = page.get_text("dict")
        blocks = _page_blocks(p_dict)
        all_lines = [l for bl in blocks for l in bl]
        words = sum(len(l["text"].split()) for l in all_lines)
        image_count += len(page.get_images())
        pages.append(PageInfo(
            number=pno + 1,
            width=page.rect.width,
            height=page.rect.height,
            has_text=words > 0,
            words=words,
        ))
        if blocks:
            sizes = sorted(l["size"] for l in all_lines)
            median = sizes[len(sizes) // 2]
            page_paras: list[Paragraph] = []
            for bl in blocks:
                page_paras.extend(
                    _group_lines_to_paragraphs(bl, pno, page.rect.width, median))
            page_paras = _merge_continuations(page_paras)
            paragraphs.extend(page_paras)
    _mark_numbered_lists(paragraphs)

    doc.close()
    return ParsedDocument(
        id=doc_id,
        filename=path.name,
        path=path,
        title=(meta.get("title") or "").strip() or path.stem.replace("_", " ").replace("-", " ").title(),
        author=(meta.get("author") or "").strip(),
        pages=pages,
        paragraphs=paragraphs,
        toc=toc_out,
        image_count=image_count,
        page_size=page_size,
    )


def ocr_pages(document: ParsedDocument, pages: list[int],
              on_page: callable | None = None) -> list[Paragraph]:
    """OCR the selected pages that have no (or no usable) text layer."""
    ocr = get_ocr()
    if not ocr.available:
        return []
    doc = fitz.open(str(document.path))
    out: list[Paragraph] = []
    done = 0
    for pno in range(doc.page_count):
        page_info = document.pages[pno]
        if page_info.has_text or (pno + 1) not in pages:
            continue
        if done >= OCREngine.MAX_PAGES:
            break
        pix = doc[pno].get_pixmap(dpi=OCR_DPI)
        import numpy as np
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:
            img = img[:, :, :3]
        lines = ocr.ocr_image(img)
        # group OCR lines into paragraphs by vertical gap
        buf: list[OCRLine] = []
        prev_y1 = None
        page_paras: list[str] = []

        for ln in lines:
            if prev_y1 is not None and ln.bbox[1] - prev_y1 > 14:
                if buf:
                    page_paras.append(" ".join(b.text for b in buf))
                    buf = []
            buf.append(ln)
            prev_y1 = ln.bbox[3]
        if buf:
            page_paras.append(" ".join(b.text for b in buf))

        for i, text in enumerate(page_paras):
            out.append(Paragraph(
                text=_clean(text),
                page=pno,
                y=0,
                size=MEDIAN_SIZE,
                kind="body",
                style_ratio=1.0,
                source="ocr",
            ))
        done += 1
        if on_page:
            on_page(pno + 1, len(pages))
    doc.close()
    return out
