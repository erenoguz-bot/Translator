"""Generates a demo English PDF so users can try the pipeline instantly."""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def make_sample_pdf(out_path: Path) -> Path:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="The State of Machine Translation",
        author="Translator Demo",
    )

    title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=22,
                           leading=27, alignment=TA_CENTER,
                           textColor=colors.HexColor("#111827"))
    sub = ParagraphStyle("S", fontName="Helvetica", fontSize=10.5,
                         leading=14, alignment=TA_CENTER,
                         textColor=colors.HexColor("#4b5563"))
    h2 = ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=14,
                        leading=18, spaceBefore=6 * mm, spaceAfter=2.5 * mm,
                        textColor=colors.HexColor("#1f2937"))
    body = ParagraphStyle("B", fontName="Helvetica", fontSize=10.3,
                          leading=15, spaceAfter=3 * mm,
                          textColor=colors.HexColor("#111827"))
    li = ParagraphStyle("L", fontName="Helvetica", fontSize=10.3,
                        leading=14, textColor=colors.HexColor("#111827"))

    story = [
        Paragraph("The State of Machine Translation", title),
        Spacer(1, 3 * mm),
        Paragraph("A short technical overview — sample document for the PDF "
                  "Translator", sub),
        Spacer(1, 8 * mm),

        Paragraph("1. Introduction", h2),
        Paragraph(
            "Machine translation has changed more in the last ten years than "
            "in the previous fifty. Statistical models that assembled "
            "translations from phrase tables have been replaced by neural "
            "networks that read a whole sentence at once. The result is text "
            "that reads far more naturally, with fewer of the stilted "
            "fragments that once gave the field a bad reputation.",
            body),
        Paragraph(
            "Today, translation runs on ordinary CPU hardware, on phones, in "
            "browsers, and inside the tools you use every day. It is also "
            "quietly becoming a building block for other systems: search "
            "engines that match queries across languages, support bots that "
            "answer in the customer's tongue, and research platforms that "
            "make scientific literature accessible worldwide.",
            body),

        Paragraph("2. How Neural Models Work", h2),
        Paragraph(
            "A modern neural machine translation model follows a simple "
            "recipe. The input sentence is split into small subword units, "
            "each unit is converted into a vector of numbers, and a stack of "
            "attention layers learns how those units relate to one another. "
            "The decoder then generates the output sentence one token at a "
            "time, weighting its attention over the most relevant parts of "
            "the source.",
            body),
        Paragraph("The main ingredients are:", body),
        ListFlowable(
            [Paragraph(t, li) for t in (
                "Subword tokenization, usually SentencePiece, so unknown "
                "words are never a problem.",
                "Encoder–decoder attention, which aligns words across "
                "languages without any hand-built rules.",
                "Large parallel corpora from public sources such as the "
                "Opus project and the Common Crawl.",
                "Int8 quantization, which shrinks models so they run on "
                "consumer hardware without losing much quality.",
            )],
            bulletType="bullet", start="•", leftIndent=6 * mm,
        ),
        Spacer(1, 4 * mm),

        Paragraph("3. Measuring Quality", h2),
        Paragraph(
            "Evaluating a translation model takes more than a single number. "
            "The table below lists the metrics that practitioners reach for "
            "most often.",
            body),
    ]

    table = Table(
        [
            ["Metric", "What it measures", "Limitation"],
            ["BLEU", "Overlap with reference translations",
             "Ignores word order and meaning"],
            ["TER", "Edits needed to match a reference",
             "Expensive to compute at scale"],
            ["COMET", "Semantic closeness with a neural scorer",
             "Needs a GPU to score large batches"],
            ["Human rating", "Fluency and adequacy by experts",
             "Slow and costly"],
        ],
        colWidths=[28 * mm, 70 * mm, 78 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d2fe")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    story.append(Spacer(1, 5 * mm))

    story += [
        Paragraph("4. Open Challenges", h2),
        Paragraph(
            "Despite the progress, a handful of problems remain stubbornly "
            "hard. The most important ones are:",
            body),
        ListFlowable(
            [Paragraph(t, li) for t in (
                "Long documents: models still drift over hundreds of pages, "
                "losing consistency in names and terminology.",
                "Rare language pairs, where parallel data is scarce and "
                "quality drops sharply.",
                "Formatting: keeping headings, tables and lists intact while "
                "the language changes is a layout problem as much as a "
                "language one.",
            )],
            bulletType="1", leftIndent=6 * mm,
        ),
        Spacer(1, 5 * mm),

        Paragraph("5. Conclusion", h2),
        Paragraph(
            "Machine translation is no longer a laboratory curiosity. It is "
            "infrastructure. The tools that combine careful document parsing "
            "with a solid neural model, exactly the kind of pipeline "
            "described in this note, are what make documents from around the "
            "world reachable to everyone.",
            body),
    ]

    doc.build(story)
    out_path.write_bytes(buf.getvalue())
    return out_path
