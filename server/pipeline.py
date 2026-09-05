"""Translation pipeline: parse → OCR → detect → translate → build outputs.

Each run is a Job executed on a worker thread; progress events are pushed to
subscribers (the SSE endpoint) as dicts.
"""
from __future__ import annotations

import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue

from . import pdf_parser, pdf_writer
from .config import KEEP_JOBS, OUTPUT_DIR
from .langid import detect_language
from .nmt import get_engine
from .ocr import get_ocr
from .pdf_parser import Paragraph, ParsedDocument


@dataclass
class Job:
    id: str
    document_id: str
    status: str = "queued"          # queued | running | done | error
    stage: str = "queued"
    progress: float = 0.0
    message: str = ""
    error: str = ""
    source_lang: str = "en"
    target_lang: str = "de"
    mode: str = "bilingual"
    auto_source: bool = False
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    outputs: dict = field(default_factory=dict)   # name -> file path
    stats: dict = field(default_factory=dict)
    _subs: set = field(default_factory=set, repr=False)

    def emit(self, stage: str, progress: float, message: str = ""):
        self.stage = stage
        self.progress = progress
        self.message = message
        for q in list(self._subs):
            try:
                q.put_nowait({
                    "event": "progress",
                    "stage": stage,
                    "progress": round(progress, 1),
                    "message": message,
                })
            except Exception:
                self._subs.discard(q)

    def subscribe(self) -> Queue:
        q: Queue = Queue(maxsize=200)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: Queue) -> None:
        self._subs.discard(q)

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 1),
            "message": self.message,
            "error": self.error,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "mode": self.mode,
            "outputs": list(self.outputs.keys()),
            "stats": self.stats,
            "elapsed": round((self.finished or time.time()) - self.created, 2),
        }


class JobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.documents: dict[str, ParsedDocument] = {}
        self._lock = threading.Lock()

    def add_document(self, doc: ParsedDocument) -> ParsedDocument:
        with self._lock:
            self.documents[doc.id] = doc
        return doc

    def create_job(self, document_id: str, **kw) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], document_id=document_id, **kw)
        with self._lock:
            self.jobs[job.id] = job
            if len(self.jobs) > KEEP_JOBS:
                for old_id in list(self.jobs)[:-KEEP_JOBS]:
                    old = self.jobs.pop(old_id)
                    for f in old.outputs.values():
                        try:
                            Path(f).unlink(missing_ok=True)
                        except Exception:
                            pass
                    try:
                        d = OUTPUT_DIR / old_id
                        if d.exists():
                            shutil.rmtree(d, ignore_errors=True)
                    except Exception:
                        pass
        return job

    def job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def document(self, doc_id: str) -> ParsedDocument | None:
        return self.documents.get(doc_id)


STORE = JobStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _select_paragraphs(doc: ParsedDocument, pages: list[int] | None,
                       ocr_paras: list[Paragraph]) -> list[Paragraph]:
    base = doc.paragraphs if pages is None else [
        p for p in doc.paragraphs if (p.page + 1) in set(pages)
    ]
    if ocr_paras:
        ocr_pages = {p.page for p in ocr_paras}
        base = [p for p in base if p.page not in ocr_pages]
    merged = list(base) + list(ocr_paras)
    merged.sort(key=lambda p: (p.page, p.y))
    return merged


# ---------------------------------------------------------------------------
# Client-side translation build (browser did the translating)
# ---------------------------------------------------------------------------


def run_client_build(doc: ParsedDocument,
                     source_lang: str,
                     target_lang: str,
                     mode: str,
                     paragraphs: list[dict]) -> Job:
    """Build outputs from client-provided translations (online mode).

    `paragraphs`: [{text, translation, kind, align, page, source?}, ...]
    """
    if not paragraphs:
        raise ValueError("No paragraphs provided.")
    for p in paragraphs:
        if "text" not in p or "translation" not in p:
            raise ValueError("Each paragraph needs 'text' and 'translation'.")
    job = STORE.create_job(
        doc.id,
        source_lang=source_lang,
        target_lang=target_lang,
        mode=mode,
    )
    job.engine_name = "online (browser)"

    def worker() -> None:
        out_dir = OUTPUT_DIR / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            job.status = "running"
            job.emit("build", 50, "Composing PDFs from browser translations…")
            info = pdf_writer.DocInfo(
                title=doc.title,
                filename=doc.filename,
                author=doc.author,
                page_count=doc.page_count,
                word_count=sum(len(str(p.get("text", "")).split())
                               for p in paragraphs),
            )
            out_paras = [
                {"text": str(p.get("text", "")),
                 "translation": str(p.get("translation", "")),
                 "kind": p.get("kind", "body"),
                 "align": p.get("align", "left"),
                 "page": int(p.get("page", 0)),
                 "source": p.get("source", "text")}
                for p in paragraphs
            ]
            base = Path(doc.filename).stem
            job.outputs["bilingual_pdf"] = str(pdf_writer.build_bilingual_pdf(
                out_paras, info, source_lang, target_lang,
                out_dir / f"{base}.bilingual.pdf"))
            job.outputs["translated_pdf"] = str(pdf_writer.build_translated_pdf(
                out_paras, info, target_lang,
                out_dir / f"{base}.translated.pdf"))
            job.outputs["text_bilingual"] = str(pdf_writer.build_txt(
                out_paras, info, "bilingual", target_lang,
                out_dir / f"{base}.bilingual.txt"))
            job.outputs["text_translation"] = str(pdf_writer.build_txt(
                out_paras, info, "translation", target_lang,
                out_dir / f"{base}.translated.txt"))
            job.outputs["json"] = str(pdf_writer.build_json(
                out_paras, info, source_lang, target_lang,
                out_dir / "result.json",
                extra={
                    "engine": "Online service (browser)",
                    "route": ["online engine (browser)"],
                    "ocr_used": any(p.get("source") == "ocr"
                                    for p in out_paras),
                    "paragraph_count": len(out_paras),
                    "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            ))
            job.stats = {
                "words": info.word_count,
                "paragraphs": len(out_paras),
                "route": ["online engine (browser)"],
                "ocr_used": any(p.get("source") == "ocr" for p in out_paras),
                "source": source_lang,
                "source_language": source_lang,
                "target": target_lang,
                "target_language": target_lang,
                "elapsed": 0,
            }
            job.status = "done"
            job.finished = time.time()
            job.emit("done", 100, "Done")
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            job.finished = time.time()
            job.emit("error", job.progress, str(e))
            traceback.print_exc()

    t = threading.Thread(target=worker, daemon=True, name=f"job-{job.id}")
    t.start()
    return job


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_translation(doc: ParsedDocument,
                    source: str,
                    target: str,
                    mode: str,
                    pages: list[int] | None = None,
                    use_ocr: bool = True,
                    engine_name: str = "auto") -> Job:
    """Validate inputs, then start the pipeline on a worker thread.

    engine_name: "auto" (local model if available, else online),
                 "local" (offline Opus-MT only) or "online".
    """
    from . import online_mt
    from .config import LOCAL_LANGUAGES

    engine = get_engine()
    auto = source == "auto"
    local_route = engine.route(source, target) if not auto else None
    force_online = engine_name == "online" and source != target
    needs_online = (target not in LOCAL_LANGUAGES
                    or (not auto and source != target and not local_route)
                    or force_online)
    if needs_online and engine_name != "local":
        if not online_mt.is_available():
            raise ValueError(
                f"No local model for this pair and the online engine is "
                f"unreachable from this server. Local pairs: "
                + ", ".join(f"{a}→{b}"
                            for a, b in engine.available_pairs))
    if engine_name == "local" and needs_online:
        raise ValueError(
            "This pair has no local model — choose the online engine.")
    job = STORE.create_job(
        doc.id,
        source_lang="auto" if auto else source,
        target_lang=target,
        mode=mode,
        auto_source=auto,
    )
    job.engine_name = "online" if needs_online else "local"

    def worker() -> None:
        out_dir = OUTPUT_DIR / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        resolved_source = source
        route: list[tuple[str, str]] = []
        try:
            job.status = "running"
            selected_pages = set(pages) if pages else set(
                p.number for p in doc.pages)

            # ---- 1. collect paragraphs ------------------------------------
            job.emit("parse", 4, "Selecting text…")
            paras = _select_paragraphs(doc, pages, [])

            # ---- 2. OCR fallback for scanned pages -------------------------
            ocr = get_ocr()
            scanned = [
                p.number for p in doc.pages
                if not p.has_text and p.number in selected_pages
            ]
            if not paras and scanned and use_ocr and not ocr.available:
                raise ValueError(
                    "The selected pages have no text layer and the OCR "
                    "engine is not available in this deployment.")
            if scanned and use_ocr and ocr.available:
                job.emit("ocr", 8, f"Running OCR on {len(scanned)} page(s)…")
                ocr_paras = pdf_parser.ocr_pages(
                    doc, scanned,
                    on_page=lambda done, total: job.emit(
                        "ocr", 8 + 14 * done / max(total, 1),
                        f"OCR page {done}/{total}…"),
                )
                if ocr_paras:
                    paras = _select_paragraphs(doc, pages, ocr_paras)
                job.emit("ocr", 22, "OCR complete")
            if not paras:
                raise ValueError(
                    "No text found on the selected pages"
                    + (" (OCR did not recover any text)." if scanned
                       else ". If this is a scanned document, make sure "
                            "OCR is enabled."))

            # ---- 3. language detection -------------------------------------
            job.emit("detect", 26, "Detecting source language…")
            if job.auto_source:
                resolved_source, _conf, how = detect_language(
                    doc.text(sorted(selected_pages)))
                job.source_lang = resolved_source
                job.message = f"Detected source language: {resolved_source} ({how})"
            if resolved_source != target:
                if job.engine_name == "online":
                    route = []  # online engine: direct pair, no local model
                else:
                    route = engine.route(resolved_source, target)
                    if not route:
                        raise ValueError(
                            f"No model for {resolved_source} → {target}. "
                            f"Available pairs: "
                            + ", ".join(f"{a}→{b}"
                                        for a, b in engine.available_pairs)
                        )

            # ---- 4. translate ----------------------------------------------
            if job.engine_name == "online" and resolved_source != target:
                from . import online_mt
                job.emit("translate", 30,
                         "Translating online (browser/server fallback)…")
                n_paras = len(paras)

                def on_batch(done, total):
                    job.emit("translate", 30 + 58 * done / max(total, 1),
                             f"Online translation… {done}/{total} chunks")

                translations = online_mt.translate_texts(
                    [p.text for p in paras], resolved_source, target,
                    on_batch=on_batch)
                for p, t in zip(paras, translations):
                    p.translation = t
                job.emit("translate", 88, "Translation complete")
            elif resolved_source == target:
                for p in paras:
                    p.translation = p.text
                job.emit("translate", 88,
                         "Source equals target — copying text…")
            else:
                total_words = max(sum(p.word_count for p in paras), 1)
                done_words = 0

                def on_sentence(i: int, n: int, orig: str, trans: str) -> None:
                    nonlocal done_words
                    done_words += len(orig.split())
                    frac = 30 + 58 * min(done_words / total_words, 1.0)
                    job.emit("translate", frac,
                             f"Translating… "
                             f"{min(done_words, total_words)}/{total_words} words")

                for i, p in enumerate(paras):
                    try:
                        p.translation = engine.translate_text(
                            resolved_source, target, p.text,
                            on_sentence=on_sentence)
                    except Exception as e:
                        raise RuntimeError(
                            f"Translation failed on paragraph {i + 1}: {e}"
                        ) from e
                job.emit("translate", 88, "Translation complete")

            route_desc = [f"{a} → {b}" for a, b in route] or (
                ["online engine"] if job.engine_name == "online"
                else ["identity"])

            # ---- 5. build outputs ------------------------------------------
            job.emit("build", 90, "Composing PDFs…")
            info = pdf_writer.DocInfo(
                title=doc.title,
                filename=doc.filename,
                author=doc.author,
                page_count=doc.page_count,
                word_count=sum(p.word_count for p in paras),
            )
            out_paras = [
                {
                    "text": p.text,
                    "translation": getattr(p, "translation", p.text),
                    "kind": p.kind,
                    "align": p.align,
                    "page": p.page,
                }
                for p in paras
            ]
            base = Path(doc.filename).stem
            job.outputs["translated_pdf"] = str(pdf_writer.build_translated_pdf(
                out_paras, info, target,
                out_dir / f"{base}.translated.pdf"))
            job.outputs["bilingual_pdf"] = str(pdf_writer.build_bilingual_pdf(
                out_paras, info, resolved_source, target,
                out_dir / f"{base}.bilingual.pdf"))
            job.outputs["text_translation"] = str(pdf_writer.build_txt(
                out_paras, info, "translation", target,
                out_dir / f"{base}.translated.txt"))
            job.outputs["text_bilingual"] = str(pdf_writer.build_txt(
                out_paras, info, "bilingual", target,
                out_dir / f"{base}.bilingual.txt"))
            job.outputs["json"] = str(pdf_writer.build_json(
                out_paras, info, resolved_source, target,
                out_dir / "result.json",
                    extra={
                        "engine": "Opus-MT (Argos, CTranslate2)",
                        "route": route_desc,
                        "ocr_used": any(p.source == "ocr" for p in paras),
                        "paragraph_count": len(out_paras),
                        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
            ))
            job.emit("build", 99, "Finalizing…")

            job.stats = {
                "paragraphs": len(out_paras),
                "words": info.word_count,
                "route": route_desc,
                "ocr_used": any(p.source == "ocr" for p in paras),
                "source_language": resolved_source,
                "target_language": target,
            }
            job.status = "done"
            job.finished = time.time()
            job.emit("done", 100, "Done")
        except Exception as e:
            job.status = "error"
            job.error = str(e)
            job.finished = time.time()
            job.emit("error", job.progress, str(e))
            traceback.print_exc()

    t = threading.Thread(target=worker, daemon=True, name=f"job-{job.id}")
    t.start()
    return job
