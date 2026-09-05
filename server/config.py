"""Central configuration and paths for the Translator server."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
EXTRACTED_DIR = MODELS_DIR / ".extracted"
FONTS_DIR = ROOT / "fonts"
WORK_DIR = ROOT / "work"
UPLOADS_DIR = WORK_DIR / "uploads"
DOCS_DIR = WORK_DIR / "docs"
OUTPUT_DIR = WORK_DIR / "output"
STATIC_DIR = ROOT / "static"

for _d in (WORK_DIR, UPLOADS_DIR, DOCS_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
OCR_DPI = 150
PREVIEW_DPI = 80
KEEP_JOBS = 20

# Languages supported end-to-end (models + output fonts + detection)
LANGUAGES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "zh": "Chinese (Simplified)",
}

# Output fonts per language (reportlab names registered in pdf_writer)
RTL_LANGS = {"ar"}
