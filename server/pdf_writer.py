"""PDF output builders (ReportLab).

Three outputs:
  - translated PDF  : styled document in the target language only
  - bilingual PDF   : original | translation in parallel columns
  - plain text / JSON exports
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import FONTS_DIR, LANGUAGES, RTL_LANGS

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

_registered = False


def _register_fonts() -> None:
    global _registered
    if _registered:
        return
    fonts = {
        "DejaVuSans": "DejaVuSans",
        "DejaVuSans-Bold": "DejaVuSans-Bold",
    }
    for name, file in fonts.items():
        p = Path(f"/usr/share/fonts/truetype/dejavu/{file}.ttf")
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(p)))
            except Exception:
                pass
    ar = FONTS_DIR / "NotoNaskhArabic-Regular.ttf"
    arb = FONTS_DIR / "NotoNaskhArabic-Bold.ttf"
    if ar.exists():
        pdfmetrics.registerFont(TTFont("NotoNaskhArabic", str(ar)))
    if arb.exists():
        pdfmetrics.registerFont(TTFont("NotoNaskhArabic-Bold", str(arb)))
    th = FONTS_DIR / "NotoSansThai-Regular.ttf"
    thb = FONTS_DIR / "NotoSansThai-Bold.ttf"
    if th.exists():
        pdfmetrics.registerFont(TTFont("NotoSansThai", str(th)))
    if thb.exists():
        pdfmetrics.registerFont(TTFont("NotoSansThai-Bold", str(thb)))
    # Built-in CJK font (no file needed)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception:
        pass
    _registered = True


def fonts_for(lang: str) -> tuple[str, str]:
    """Return (regular, bold) font names for a language."""
    _register_fonts()
    if lang.startswith("zh"):
        return "STSong-Light", "STSong-Light"
    if lang == "ar":
        return "NotoNaskhArabic", "NotoNaskhArabic-Bold"
    if lang == "th":
        return "NotoSansThai", "NotoSansThai-Bold"
    return "DejaVuSans", "DejaVuSans-Bold"


def shape_text(text: str, lang: str) -> str:
    """Apply Arabic reshaping + RTL reordering so static PDFs render right."""
    if lang not in RTL_LANGS:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

ALIGN = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}


def _style_for(kind: str, lang: str, base: dict) -> ParagraphStyle:
    reg, bold = fonts_for(lang)
    if kind == "title":
        st = ParagraphStyle(
            "Title", fontName=bold, fontSize=21, leading=26,
            spaceAfter=6 * mm, spaceBefore=2 * mm,
            alignment=base.get("align", TA_CENTER),
            textColor=colors.HexColor("#111827"),
        )
    elif kind == "heading":
        st = ParagraphStyle(
            "Heading", fontName=bold, fontSize=13.5, leading=18,
            spaceAfter=2.6 * mm, spaceBefore=5.5 * mm,
            alignment=base.get("align", TA_LEFT),
            textColor=colors.HexColor("#1f2937"),
        )
    elif kind == "caption":
        st = ParagraphStyle(
            "Caption", fontName=reg, fontSize=8.5, leading=11,
            spaceAfter=2.5 * mm, alignment=TA_LEFT,
            textColor=colors.HexColor("#4b5563"),
        )
    else:  # body / list
        st = ParagraphStyle(
            "Body", fontName=reg, fontSize=10.3, leading=15,
            spaceAfter=3 * mm, alignment=base.get("align", TA_LEFT),
            textColor=colors.HexColor("#111827"),
        )
        if kind == "list":
            st.leftIndent = 5 * mm
    return st


def _split_for_cell(text: str, limit: int = 1400) -> list[str]:
    """Last line of defense for PDF flowables: split oversized cell text."""
    if len(text or "") <= limit:
        return [text or ""]
    out: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + limit, n)
        if end < n:
            cut = text.rfind(" ", start + limit // 2, end)
            end = cut if cut > start else end
        out.append(text[start:end].strip())
        start = end
    return [t for t in out if t] or [""]


def _build_flowables(paras: list[dict], lang: str,
                     text_key: str = "text") -> list:
    """paradict: text, translation, kind, align"""
    flow = []
    for p in paras:
        for piece in _split_for_cell(p[text_key], 3000):
            text = shape_text(piece, lang)
            st = _style_for(p.get("kind", "body"), lang,
                            {"align": ALIGN.get(p.get("align", "left"),
                                                TA_LEFT)})
            flow.append(Paragraph(esc(text), st))
    return flow


def _footer(canv, doc, label: str):
    canv.saveState()
    canv.setFont("DejaVuSans", 8)
    canv.setFillColor(colors.HexColor("#9ca3af"))
    canv.drawString(MARGIN, 12 * mm, label)
    canv.drawRightString(PAGE_W - MARGIN, 12 * mm, f"Page {canv.getPageNumber()}")
    canv.restoreState()


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

@dataclass
class DocInfo:
    title: str
    filename: str
    author: str = ""
    page_count: int = 0
    word_count: int = 0


def build_translated_pdf(paras: list[dict], info: DocInfo, target_lang: str,
                         out_path: Path) -> Path:
    """paras: [{'text','kind','align'}...] already translated."""
    _register_fonts()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=info.title, author=info.author or "PDF Translator",
    )
    label = f"Translated to {LANGUAGES.get(target_lang, target_lang)}"
    doc.build(_build_flowables(paras, target_lang, text_key="translation"),
              onFirstPage=lambda c, d: _footer(c, d, label),
              onLaterPages=lambda c, d: _footer(c, d, label))
    return out_path


def build_bilingual_pdf(paras: list[dict], info: DocInfo, src_lang: str,
                        tgt_lang: str, out_path: Path) -> Path:
    """paras: [{'text','translation','kind','align'}...]."""
    _register_fonts()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title=info.title, author=info.author or "PDF Translator",
    )
    src_reg, _ = fonts_for(src_lang)
    tgt_reg, _ = fonts_for(tgt_lang)

    style_src = ParagraphStyle(
        "biSrc", fontName=src_reg, fontSize=9.6, leading=13.5,
        textColor=colors.HexColor("#1f2937"),
    )
    style_tgt = ParagraphStyle(
        "biTgt", fontName=tgt_reg, fontSize=9.6, leading=13.5,
        textColor=colors.HexColor("#111827"),
    )
    style_head = ParagraphStyle(
        "biHead", fontName=fonts_for(src_lang)[1], fontSize=10, leading=13,
        textColor=colors.HexColor("#312e81"),
    )

    story: list = []
    label = f"{LANGUAGES.get(src_lang, src_lang)}  →  {LANGUAGES.get(tgt_lang, tgt_lang)}"
    story.append(Paragraph(esc(info.title), ParagraphStyle(
        "biTitle", fontName=fonts_for(tgt_lang)[1], fontSize=16, leading=20,
        spaceAfter=4 * mm, textColor=colors.HexColor("#111827"))))

    col_w = (PAGE_W - 28 * mm) / 2
    for p in paras:
        kind = p.get("kind", "body")
        if kind in ("title", "heading"):
            head = Paragraph(
                f"■  {esc(shape_text(p['text'], src_lang))}",
                style_head,
            )
            bar = Table([[head]], colWidths=[PAGE_W - 28 * mm])
            bar.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2ff")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(Spacer(1, 3 * mm))
            story.append(bar)
            story.append(Spacer(1, 1.5 * mm))
            continue
        # one table per chunk → rows can never exceed the page height
        src_parts = _split_for_cell(p["text"])
        tgt_parts = _split_for_cell(p["translation"])
        while len(tgt_parts) < len(src_parts):
            tgt_parts.append("")
        while len(src_parts) < len(tgt_parts):
            src_parts.append("")
        for src_piece, tgt_piece in zip(src_parts, tgt_parts):
            cell_src = Paragraph(
                esc(shape_text(src_piece, src_lang)), style_src)
            cell_tgt = Paragraph(
                esc(shape_text(tgt_piece, tgt_lang)), style_tgt)
            t = Table(
                [[cell_src, cell_tgt]],
                colWidths=[col_w, col_w],
            )
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5,
                 colors.HexColor("#e5e7eb")),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f9fafb")),
            ]))
            story.append(t)

    doc.build(story,
              onFirstPage=lambda c, d: _footer(c, d, f"Bilingual · {label}"),
              onLaterPages=lambda c, d: _footer(c, d, f"Bilingual · {label}"))
    return out_path


def build_txt(paras: list[dict], info: DocInfo, mode: str, lang: str,
              out_path: Path) -> Path:
    """mode: 'translation' | 'original' | 'bilingual'"""
    lines: list[str] = [f"# {info.title}", f"# {info.filename}", ""]
    for p in paras:
        if mode == "translation":
            lines.append(shape_text(p["translation"], lang))
            lines.append("")
        elif mode == "original":
            lines.append(p["text"])
            lines.append("")
        else:
            lines.append(p["text"])
            lines.append(shape_text(p["translation"], lang))
            lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def build_json(paras: list[dict], info: DocInfo, src_lang: str, tgt_lang: str,
               out_path: Path, extra: dict | None = None) -> Path:
    payload = {
        "document": {
            "filename": info.filename,
            "title": info.title,
            "author": info.author,
            "pages": info.page_count,
            "word_count": info.word_count,
        },
        "source_language": src_lang,
        "target_language": tgt_lang,
        "paragraphs": [
            {k: p.get(k) for k in
             ("page", "kind", "align", "source", "size", "text", "translation")}
            for p in paras
        ],
    }
    if extra:
        payload.update(extra)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return out_path
