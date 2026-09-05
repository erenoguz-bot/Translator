"""OCR for scanned / image-only PDF pages (RapidOCR, onnxruntime, offline).

The engine is created lazily on first use so that text-only workflows pay
zero cost. PP-OCRv6 covers Latin, Cyrillic and CJK scripts; quality for
other scripts is best-effort.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

log = logging.getLogger("translator.ocr")


@dataclass
class OCRLine:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    score: float


class OCREngine:
    MAX_PAGES = 40  # safety valve per job

    def __init__(self) -> None:
        self._ocr = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        try:
            import rapidocr  # noqa: F401
            return True
        except Exception:
            return False

    def _get(self):
        if self._ocr is None:
            with self._lock:
                if self._ocr is None:
                    from rapidocr import RapidOCR
                    self._ocr = RapidOCR()
        return self._ocr

    def ocr_image(self, image) -> list[OCRLine]:
        """Run OCR on a numpy image (HxWx3 RGB) or ndarray from OpenCV."""
        ocr = self._get()
        result = ocr(image)
        if result is None:
            return []
        out: list[OCRLine] = []
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or txts is None:
            return []
        for i, txt in enumerate(txts):
            if not txt or not txt.strip():
                continue
            box = boxes[i]
            x0 = float(min(p[0] for p in box))
            y0 = float(min(p[1] for p in box))
            x1 = float(max(p[0] for p in box))
            y1 = float(max(p[1] for p in box))
            score = float(scores[i]) if scores is not None else 1.0
            out.append(OCRLine(text=txt.strip(), bbox=(x0, y0, x1, y1), score=score))
        # reading order: top to bottom, then left to right
        out.sort(key=lambda l: (round(l.bbox[1] / 8.0), l.bbox[0]))
        return out


_engine: OCREngine | None = None
_engine_lock = threading.Lock()


def get_ocr() -> OCREngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = OCREngine()
        return _engine
