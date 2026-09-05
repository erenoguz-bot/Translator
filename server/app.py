"""FastAPI application: REST + SSE endpoints and the static web UI."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import pdf_parser, sample_doc
from .config import (
    DOCS_DIR,
    LANGUAGES,
    MAX_UPLOAD_BYTES,
    PREVIEW_DPI,
    STATIC_DIR,
    UPLOADS_DIR,
)
from .nmt import get_engine
from .ocr import get_ocr
from .pipeline import STORE, run_translation

app = FastAPI(title="PDF Parser & Translator", version="1.0.0")

_PREVIEW_CACHE: dict[str, tuple[float, bytes]] = {}
_CACHE_LIMIT = 24


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health():
    engine = get_engine()
    return {
        "ok": True,
        "engine": "Opus-MT (Argos, CTranslate2)",
        "models": engine.stats(),
        "ocr": get_ocr().available,
        "languages": LANGUAGES,
    }


@app.get("/api/languages")
def languages():
    engine = get_engine()
    pairs = sorted(f"{a}-{b}" for a, b in engine.available_pairs)
    return {
        "languages": LANGUAGES,
        "pairs": pairs,
        "pivot": "unlisted pairs are routed through English when possible",
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", name or "document.pdf").strip()
    return name or "document.pdf"


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 100 MB).")
    if len(data) < 4 or data[:4] != b"%PDF":
        raise HTTPException(400, "Not a valid PDF file.")

    doc_id = uuid.uuid4().hex[:12]
    safe = _safe_name(file.filename)
    dest = UPLOADS_DIR / f"{doc_id}_{safe}"
    dest.write_bytes(data)

    try:
        doc = pdf_parser.parse_pdf(dest, doc_id)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Could not parse PDF: {e}")

    STORE.add_document(doc)
    return doc.summary()


@app.post("/api/documents/sample")
def sample_document():
    """Generate the built-in demo document (English, ~4 pages)."""
    doc_id = uuid.uuid4().hex[:12]
    dest = DOCS_DIR / f"{doc_id}_sample.pdf"
    sample_doc.make_sample_pdf(dest)
    doc = pdf_parser.parse_pdf(dest, doc_id)
    STORE.add_document(doc)
    return doc.summary()


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    doc = STORE.document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found (server restarted?).")
    return doc.summary()


@app.get("/api/documents/{doc_id}/page/{page_number}")
def page_preview(doc_id: str, page_number: int):
    doc = STORE.document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found.")
    if not (1 <= page_number <= doc.page_count):
        raise HTTPException(404, "Page out of range.")
    key = f"{doc_id}:{page_number}"
    hit = _PREVIEW_CACHE.get(key)
    if hit and time.time() - hit[0] < 3600:
        return Response(hit[1], media_type="image/png")
    import pymupdf as fitz
    fdoc = fitz.open(str(doc.path))
    try:
        pix = fdoc[page_number - 1].get_pixmap(dpi=PREVIEW_DPI)
    finally:
        fdoc.close()
    if len(_PREVIEW_CACHE) >= _CACHE_LIMIT:
        oldest = min(_PREVIEW_CACHE, key=lambda k: _PREVIEW_CACHE[k][0])
        _PREVIEW_CACHE.pop(oldest, None)
    _PREVIEW_CACHE[key] = (time.time(), pix.tobytes("png"))
    return Response(pix.tobytes("png"), media_type="image/png")


# ---------------------------------------------------------------------------
# Translation jobs
# ---------------------------------------------------------------------------


def _parse_page_range(value: str | None, page_count: int) -> list[int] | None:
    if not value or value.strip().lower() in ("all", ""):
        return None
    out: list[int] = []
    for part in re.split(r"[,;]+", value):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(max(1, a), min(page_count, b) + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise HTTPException(400, f"Bad page range: {part}")
    if not out:
        raise HTTPException(400, "Empty page range.")
    return sorted({p for p in out if 1 <= p <= page_count}) or None


@app.post("/api/documents/{doc_id}/translate")
def start_translation(doc_id: str, payload: dict):
    doc = STORE.document(doc_id)
    if not doc:
        raise HTTPException(404, "Document not found (server restarted?).")
    source = str(payload.get("source", "auto"))
    target = str(payload.get("target", ""))
    mode = str(payload.get("mode", "bilingual"))
    use_ocr = bool(payload.get("ocr", True))
    if source not in ("auto", *LANGUAGES):
        raise HTTPException(400, f"Unknown source language: {source}")
    if target not in LANGUAGES:
        raise HTTPException(400, f"Unknown target language: {target}")
    if mode not in ("bilingual", "translated"):
        raise HTTPException(400, "mode must be 'bilingual' or 'translated'")
    pages = _parse_page_range(payload.get("pages"), doc.page_count)

    job = run_translation(doc, source, target, mode, pages=pages, use_ocr=use_ocr)
    return job.snapshot()


def _sse(job) -> StreamingResponse:
    import queue as _queue

    q = job.subscribe()

    async def stream():
        loop = asyncio.get_running_loop()
        try:
            yield f"data: {json.dumps(job.snapshot())}\n\n"
            while True:
                try:
                    # blocking get (2 s) on a worker thread → clean heartbeat
                    ev = await loop.run_in_executor(None, q.get, True, 2.0)
                    yield f"data: {json.dumps(ev)}\n\n"
                    if ev.get("event") in ("done", "error"):
                        break
                except _queue.Empty:
                    yield f"data: {json.dumps(job.snapshot())}\n\n"
                    if job.status in ("done", "error"):
                        break
        finally:
            job.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str):
    job = STORE.job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return _sse(job)


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = STORE.job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return job.snapshot()


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    job = STORE.job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status != "done":
        return JSONResponse(
            {"status": job.status, "error": job.error,
             "progress": job.progress, "stage": job.stage},
            status_code=202,
        )
    payload = json.loads(Path(job.outputs["json"]).read_text(encoding="utf-8"))
    payload["job"] = job.snapshot()
    return payload


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

_FORMATS = {
    "bilingual": "bilingual_pdf",
    "translated": "translated_pdf",
    "txt-bilingual": "text_bilingual",
    "txt-translation": "text_translation",
    "json": "json",
}


@app.get("/api/jobs/{job_id}/download")
def job_download(job_id: str, format: str = Query("bilingual")):
    job = STORE.job(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    if job.status != "done":
        raise HTTPException(409, "Job is not finished yet.")
    key = _FORMATS.get(format)
    if not key or key not in job.outputs:
        raise HTTPException(400,
                            f"Unknown format. Use one of: {', '.join(_FORMATS)}")
    path = Path(job.outputs[key])
    if not path.exists():
        raise HTTPException(410, "Output file is gone (pruned).")
    media = {
        "bilingual_pdf": "application/pdf",
        "translated_pdf": "application/pdf",
        "text_bilingual": "text/plain; charset=utf-8",
        "text_translation": "text/plain; charset=utf-8",
        "json": "application/json",
    }[key]
    return FileResponse(str(path), media_type=media,
                        filename=path.name)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def unhandled(_: object, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})
