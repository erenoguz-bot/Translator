# 📄 PDF Parser & Translator

A full-featured, **100% local** PDF parser and translator: upload a PDF (or a
*scanned* one), and get a translated document with original layout — plus a
bilingual side-by-side PDF, plain text and structured JSON exports.

```
PDF in  ──▶  PyMuPDF layout parser  ──▶  (RapidOCR for scanned pages)
                                              │
                              language detection (script + statistical)
                                              │
                              Opus-MT neural MT (Argos models, CTranslate2)
                                              │
                  translated PDF · bilingual PDF · TXT · JSON out
```

Everything runs offline on CPU: no API keys, no cloud calls, no telemetry.

---

## Features

### Parser
- Layout-aware text extraction with **PyMuPDF**: paragraphs reconstructed from
  PDF blocks/lines, keeping **font size, bold/italic, alignment**
  (left/center/right) and position.
- Automatic detection of **titles, headings, body text, bullet & numbered
  lists, captions** (size-ratio + pattern heuristics).
- Full document metadata: title, author, page count & sizes, word counts per
  page, table of contents, embedded image count, encryption check.
- **Scanned PDF support** — pages without a text layer are detected and run
  through **RapidOCR** (PP-OCRv6, onnxruntime) automatically.
- Page thumbnails rendered server-side for the UI.

### Translator
- **Offline neural MT**: Opus-MT models in Argos packaging, served by
  **CTranslate2** (int8) + SentencePiece.
- **9 languages**: English, German, French, Spanish, Italian, Portuguese,
  Russian, Arabic, Chinese (Simplified) — 16 direct model pairs, and *every*
  pair of the 9 languages is reachable via automatic **English pivoting**.
- Sentence-level batching with token budgets; live per-word progress via SSE.
- Source-language **auto-detection** (script fast paths for CJK/Cyrillic/
  Arabic + statistical detection for Latin scripts).
- **Arabic output** is reshaped + RTL-reordered (`arabic-reshaper`,
  `python-bidi`) so static PDFs render correctly.
- **CJK-safe PDF output** (built-in STSong CID font; Noto Naskh Arabic for
  Arabic; DejaVu for everything else).

### Outputs
| Format | Description |
|---|---|
| **Bilingual PDF** | Original and translation in parallel columns, heading bars, page footers |
| **Translated PDF** | The document fully in the target language, styled (title/headings/lists/alignment preserved) |
| **Plain text** | Translation only, or original+translation pairs |
| **JSON** | Full structured result: metadata, route, per-paragraph text/translation/kind/align/page |

### Web UI
- Drag & drop upload, page thumbnails, sample-document generator
- Live progress stream (parse → OCR → detect → translate → build)
- Side-by-side result viewer, one-click downloads
- Page-range selection (`1-3,5`), OCR toggle, output-mode choice

---

## Quick start

```bash
# 1. environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. models (~1.4 GB, 16 pairs) — fetched from the official
#    LibreTranslate GitHub mirror (see scripts/fetch_models.py)
.venv/bin/python scripts/fetch_models.py

# 3. run
.venv/bin/python run.py            # → http://localhost:8000
```

Then open <http://localhost:8000>, drop a PDF (or click
*✨ Try the sample document*), pick a target language, and translate.

### API (all used by the UI)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | engine status, model pairs, OCR availability |
| `GET` | `/api/languages` | languages + available pairs |
| `POST` | `/api/documents` | upload a PDF (multipart `file`) → parsed summary |
| `POST` | `/api/documents/sample` | generate the built-in demo document |
| `GET` | `/api/documents/{id}` | parsed summary (paragraphs, pages, TOC…) |
| `GET` | `/api/documents/{id}/page/{n}` | PNG thumbnail of page n |
| `POST` | `/api/documents/{id}/translate` | start a job `{source, target, mode, pages, ocr}` |
| `GET` | `/api/jobs/{id}` | job status |
| `GET` | `/api/jobs/{id}/events` | **SSE** live progress stream |
| `GET` | `/api/jobs/{id}/result` | full result JSON |
| `GET` | `/api/jobs/{id}/download?format=…` | `bilingual` · `translated` · `txt-bilingual` · `txt-translation` · `json` |

```bash
DOC=$(curl -s -X POST localhost:8000/api/documents/sample | jq -r .id)
JOB=$(curl -s -X POST localhost:8000/api/documents/$DOC/translate \
      -H 'content-type: application/json' \
      -d '{"source":"auto","target":"de","mode":"bilingual"}' | jq -r .id)
curl -sN localhost:8000/api/jobs/$JOB/events          # watch progress
curl -sOJ localhost:8000/api/jobs/$JOB/download?format=bilingual
```

---

## Project layout

```
run.py                  server entry point (uvicorn)
requirements.txt
server/
  app.py                FastAPI app: REST + SSE + static UI
  config.py             paths, languages, limits
  pdf_parser.py         PyMuPDF layout parsing, paragraph model, OCR glue
  ocr.py                RapidOCR wrapper (lazy, offline)
  langid.py             language detection (script + statistical)
  nmt.py                CTranslate2/SentencePiece engine, model registry,
                        sentence batching, English pivoting
  pdf_writer.py         ReportLab builders (translated / bilingual / txt / json)
  pipeline.py           job orchestration + progress events
  sample_doc.py         built-in demo document generator
static/                 web UI (vanilla JS, no build step)
models/                 .argosmodel files (gitignored, fetched by script)
scripts/fetch_models.py model downloader (partial GitHub clone)
tests/test_pipeline.py  end-to-end tests (parse → OCR → MT → PDFs)
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

19 end-to-end tests cover parsing, language detection, NMT routing &
translation, pivoting, scanned-PDF OCR, and the generated PDFs (content +
validity).

## Notes & limitations

- Models are 6-layer Opus-MT (Argos) — fast on CPU (~100–150 words/s) with
  fluent but not frontier quality. Very short, out-of-domain fragments
  (e.g. some headings) may pass through untranslated.
- PDF output is a **reconstruction** of the source (styled text flow), not a
  pixel-perfect layout clone; embedded images are not re-placed.
- Arabic text in HTML/TXT/JSON is stored in standard Unicode (browsers render
  it correctly); in static PDFs it is pre-reshaped, which is the best a
  non-CT font engine can do.
- Job state is in-memory per process (single uvicorn worker by design);
  restarting the server clears documents/jobs.

## License

- Application code: MIT (see below).
- Translation models: [Opus-MT](https://github.com/Helsinki-NLP/Opus-MT)
  (CC-BY / OPUS-1.0) in [Argos](https://argos-translate.readthedocs.io/)
  packaging.
- Fonts: DejaVu (public domain), Noto Naskh Arabic (OFL).
- OCR: PP-OCRv6 via RapidOCR (Apache-2.0).

```
MIT License

Copyright (c) 2026 Translator

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
