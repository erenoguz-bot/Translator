"""Language detection tuned to the supported language set.

Script-based fast paths (CJK / Cyrillic / Arabic) plus `langdetect` for
Latin-script languages.
"""
from __future__ import annotations

from .config import LANGUAGES

try:
    import langdetect
    from langdetect import DetectorFactory
    DetectorFactory.seed = 7  # deterministic results
except Exception:  # pragma: no cover
    langdetect = None

def _in_ranges(ord_c: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= ord_c <= hi for lo, hi in ranges)


_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))
_CYRILLIC_RANGES = ((0x0400, 0x04FF),)
_ARABIC_RANGES = ((0x0600, 0x06FF), (0xFB50, 0xFDFF))


def _script_ratio(text: str, ranges: tuple[tuple[int, int], ...]) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    hits = sum(1 for c in letters if _in_ranges(ord(c), ranges))
    return hits / len(letters)


def detect_language(text: str) -> tuple[str, float, str]:
    """Return (code, confidence, method). Falls back to 'en'."""
    text = (text or "").strip()
    if len(text) < 12:
        return "en", 0.3, "fallback"

    if _script_ratio(text, _CJK_RANGES) > 0.25:
        return "zh", 0.95, "script"
    if _script_ratio(text, _CYRILLIC_RANGES) > 0.25:
        return "ru", 0.9, "script"
    if _script_ratio(text, _ARABIC_RANGES) > 0.25:
        return "ar", 0.9, "script"

    latin = text[:4000]
    if langdetect is not None:
        try:
            code = langdetect.detect(latin)
        except Exception:
            code = None
        if code in LANGUAGES:
            # Confidence is heuristic (langdetect has no scores)
            return code, 0.75, "statistical"
        # langdetect sometimes returns 'nl', 'sv', ... which we can't
        # translate; map near-matches.
        near = {"nl": "en", "sv": "en", "da": "en", "no": "en"}
        if code in near:
            return near[code], 0.4, "statistical"
    return "en", 0.5, "fallback"
