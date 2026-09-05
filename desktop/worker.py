"""Background translation worker (QThread) for the desktop app.

Reuses the exact same engine as the web server: parser, OCR, language
detection, NMT and PDF writers from the `server` package.
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from server import pdf_parser, pdf_writer
from server.langid import detect_language
from server.nmt import get_engine
from server.ocr import get_ocr
from server.pdf_parser import ParsedDocument
from server.pipeline import _select_paragraphs


class TranslateWorker(QObject):
    """Runs the full pipeline off the GUI thread."""

    progress = Signal(str, float, str)      # stage, 0-100, message
    finished = Signal(dict)                 # result payload
    failed = Signal(str)                    # error message

    def __init__(self, doc: ParsedDocument, source: str, target: str,
                 mode: str, pages: list[int] | None, use_ocr: bool,
                 out_dir: Path, engine_name: str = "auto"):
        super().__init__()
        self.doc = doc
        self.source = source
        self.target = target
        self.mode = mode
        self.pages = pages
        self.use_ocr = use_ocr
        self.out_dir = Path(out_dir)
        self.engine_name = engine_name

    # ------------------------------------------------------------------

    def run(self) -> None:
        engine = get_engine()
        started = time.time()
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            selected_pages = set(self.pages) if self.pages else set(
                p.number for p in self.doc.pages)

            # 1. parse/select ------------------------------------------------
            self.progress.emit("parse", 4, "Selecting text…")
            paras = _select_paragraphs(self.doc, self.pages, [])

            # 2. OCR for scanned pages ---------------------------------------
            ocr = get_ocr()
            scanned = [
                p.number for p in self.doc.pages
                if not p.has_text and p.number in selected_pages
            ]
            if not paras and scanned and self.use_ocr and not ocr.available:
                raise RuntimeError(
                    "The selected pages have no text layer and OCR is "
                    "not available.")
            if scanned and self.use_ocr and ocr.available:
                self.progress.emit("ocr", 8,
                                   f"Running OCR on {len(scanned)} page(s)…")
                ocr_paras = pdf_parser.ocr_pages(
                    self.doc, scanned,
                    on_page=lambda done, total: self.progress.emit(
                        "ocr", 8 + 14 * done / max(total, 1),
                        f"OCR page {done}/{total}…"),
                )
                if ocr_paras:
                    paras = _select_paragraphs(self.doc, self.pages,
                                               ocr_paras)
                self.progress.emit("ocr", 22, "OCR complete")
            if not paras:
                raise RuntimeError(
                    "No text found on the selected pages"
                    + (" (OCR did not recover any text)." if scanned else
                       ". If this is a scanned document, enable OCR."))

            # 3. detect -------------------------------------------------------
            self.progress.emit("detect", 26, "Detecting source language…")
            resolved = self.source
            if self.source == "auto":
                resolved, _conf, how = detect_language(
                    self.doc.text(sorted(selected_pages)))
            if resolved != self.target:
                if self.engine_name == "online":
                    route = [[resolved, self.target]]
                else:
                    route = engine.route(resolved, self.target)
                    if not route:
                        raise RuntimeError(
                            f"No model for {resolved} → {self.target}. "
                            "Available pairs: "
                            + ", ".join(f"{a}→{b}"
                                        for a, b in
                                        engine.available_pairs))
            else:
                route = []

            # 4. translate ----------------------------------------------------
            if self.engine_name == "online" and resolved != self.target:
                from server import online_mt
                n = len(paras)

                def on_batch(done, total):
                    self.progress.emit(
                        "translate", 30 + 58 * done / max(total, 1),
                        f"Online translation… {done}/{total} chunks")

                translations = online_mt.translate_texts(
                    [p.text for p in paras], resolved, self.target,
                    on_batch=on_batch)
                for p, t in zip(paras, translations):
                    p.translation = t
                self.progress.emit("translate", 88, "Translation complete")
            elif resolved == self.target:
                for p in paras:
                    p.translation = p.text
                self.progress.emit("translate", 88,
                                   "Source equals target — copying text…")
            else:
                total_words = max(sum(p.word_count for p in paras), 1)
                state = {"done": 0}

                def on_sentence(i, n, orig, trans):
                    state["done"] += len(orig.split())
                    frac = 30 + 58 * min(state["done"] / total_words, 1.0)
                    self.progress.emit(
                        "translate", frac,
                        f"Translating… {min(state['done'], total_words)}"
                        f"/{total_words} words")

                for i, p in enumerate(paras):
                    p.translation = engine.translate_text(
                        resolved, self.target, p.text,
                        on_sentence=on_sentence)
                self.progress.emit("translate", 88, "Translation complete")

            # 5. build outputs ------------------------------------------------
            self.progress.emit("build", 90, "Composing PDFs…")
            info = pdf_writer.DocInfo(
                title=self.doc.title,
                filename=self.doc.filename,
                author=self.doc.author,
                page_count=self.doc.page_count,
                word_count=sum(p.word_count for p in paras),
            )
            out_paras = [
                {"text": p.text,
                 "translation": getattr(p, "translation", p.text),
                 "kind": p.kind,
                 "align": p.align,
                 "page": p.page,
                 "source": p.source}
                for p in paras
            ]
            base = Path(self.doc.filename).stem
            outputs = {
                "bilingual_pdf": str(pdf_writer.build_bilingual_pdf(
                    out_paras, info, resolved, self.target,
                    self.out_dir / f"{base}.bilingual.pdf")),
                "translated_pdf": str(pdf_writer.build_translated_pdf(
                    out_paras, info, self.target,
                    self.out_dir / f"{base}.translated.pdf")),
                "text_bilingual": str(pdf_writer.build_txt(
                    out_paras, info, "bilingual", self.target,
                    self.out_dir / f"{base}.bilingual.txt")),
                "text_translation": str(pdf_writer.build_txt(
                    out_paras, info, "translation", self.target,
                    self.out_dir / f"{base}.translated.txt")),
            }

            self.progress.emit("build", 99, "Finalizing…")
            self.finished.emit({
                "paragraphs": out_paras,
                "outputs": outputs,
                "stats": {
                    "words": info.word_count,
                    "paragraphs": len(out_paras),
                    "route": [f"{a} → {b}" for a, b in route] or ["identity"],
                    "ocr_used": any(p.source == "ocr" for p in paras),
                    "source": resolved,
                    "target": self.target,
                    "engine": ("Online service (Google)"
                               if self.engine_name == "online"
                               else "Opus-MT (Argos, CTranslate2) — 100% local"),
                    "elapsed": round(time.time() - started, 2),
                },
            })
            self.progress.emit("done", 100, "Done")
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))
