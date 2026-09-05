"""Optional *online* translation via the free Google web endpoint.

Used as a fallback for language pairs that have no local Opus-MT model
(e.g. Turkish). Two call paths exist:

  1. Server-side  — `translate_texts()` (used when the server itself has
     internet access, e.g. when the user runs the app on their machine)
  2. Browser-side — the web UI can call the same endpoint directly from
     the user's browser and then hand the translations to the server for
     PDF building (`POST /api/documents/{id}/build`).

The endpoint is unofficial and rate-limited; treat it as a best-effort
fallback and keep the local models as the default engine.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

# Languages supported in online mode (code → name).
ONLINE_LANGUAGES = {
    "tr": "Turkish",
    "nl": "Dutch",
    "pl": "Polish",
    "uk": "Ukrainian",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "th": "Thai",
    "hi": "Hindi",
    "ro": "Romanian",
    "hu": "Hungarian",
    "cs": "Czech",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "el": "Greek",
    "he": "Hebrew",
    "fa": "Persian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "sq": "Albanian",
    "be": "Belarusian",
    "mn": "Mongolian",
    "kk": "Kazakh",
    "uz": "Uzbek",
    "az": "Azerbaijani",
    "hy": "Armenian",
    "ka": "Georgian",
    "my": "Burmese",
    "lo": "Lao",
    "km": "Khmer",
    "ms": "Malay",
    "fil": "Filipino",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "mr": "Marathi",
    "gu": "Gujarati",
    "ur": "Urdu",
    "ne": "Nepali",
    "sw": "Swahili",
    "af": "Afrikaans",
    "ca": "Catalan",
    "gl": "Galician",
    "is": "Icelandic",
    "mt": "Maltese",
    "ga": "Irish",
    "cy": "Welsh",
    "sr": "Serbian",
    "bs": "Bosnian",
    "mk": "Macedonian",
    "tt": "Tatar",
    "ug": "Uyghur",
}

_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
BATCH_SIZE = 12
DELAY_S = 0.15

_lock = threading.Lock()
_available: bool | None = None


def is_available(timeout: float = 3.0) -> bool:
    """Probe the endpoint once (cached)."""
    global _available
    with _lock:
        if _available is not None:
            return _available
        try:
            translate_texts(["ping"], "en", "tr", timeout=timeout)
            _available = True
        except Exception:
            _available = False
        return _available


def _build_url(texts: list[str], src: str, tgt: str) -> str:
    q = urllib.parse.urlencode(
        {"client": "gtx", "sl": src if src and src != "auto" else "auto",
         "tl": tgt, "dt": "t"})
    q += "&" + "&".join(
        f"q={urllib.parse.quote(t, safe='')}" for t in texts)
    return f"{_ENDPOINT}?{q}"


def translate_texts(texts: list[str], src: str, tgt: str,
                    timeout: float = 20.0,
                    on_batch=None) -> list[str]:
    """Translate a list of strings (batches of ≤12 per request)."""
    out: list[str] = [""] * len(texts)
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i:i + BATCH_SIZE]
        req = urllib.request.Request(
            _build_url(chunk, src, tgt),
            headers={"User-Agent": "Mozilla/5.0 (PDF-Translator)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rows = data[0]
        for j, t in enumerate(chunk):
            if not t.strip():
                out[i + j] = t
                continue
            out[i + j] = "".join(seg[0] for seg in rows[j] if seg and seg[0])
        if on_batch:
            on_batch(min(i + BATCH_SIZE, len(texts)), len(texts))
        time.sleep(DELAY_S)
    return out
