"""Neural machine translation engine.

Runs fully offline on Argos/Opus-MT models (CTranslate2 + SentencePiece).
Model packages are `.argosmodel` zip archives found in `models/`; they are
extracted lazily on first use and kept in `models/.extracted/`.
"""
from __future__ import annotations

import json
import re
import threading
import time
import zipfile
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import ctranslate2
import sentencepiece

from .config import EXTRACTED_DIR, MODELS_DIR

# ---------------------------------------------------------------------------
# Sentence splitting (heuristic, no external NLP deps)
# ---------------------------------------------------------------------------

_LATIN_SENT_END = re.compile(
    r"(?<=[.!?…])\s+(?=[A-Z0-9\"'«“‘(\[])|(?<=[.!?…])\n+"
)
_CJK_SENT_END = re.compile(r"(?<=[。！？；])\s*")
_PUNCT_SPLIT = re.compile(r"(?<=[,;:—–])\s+")


def _split_sentences_latin(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    parts = _LATIN_SENT_END.split(text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Split very long sentences at comma boundaries so the model never
        # sees an absurdly long input.
        if len(p) > 600:
            subs = _PUNCT_SPLIT.split(p)
            buf = ""
            for s in subs:
                if buf and len(buf) + len(s) + 1 > 450:
                    out.append(buf.strip())
                    buf = s
                else:
                    buf = f"{buf} {s}".strip()
            if buf:
                out.append(buf.strip())
        else:
            out.append(p)
    return out


def _split_sentences_cjk(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = [p.strip() for p in _CJK_SENT_END.split(text) if p.strip()]
    out: list[str] = []
    for p in parts:
        # CJK has no spaces; cap chunk length by character count.
        while len(p) > 300:
            cut = p.rfind("，", 0, 300)
            if cut < 120:
                cut = 300
            out.append(p[:cut].strip())
            p = p[cut:].lstrip("，、 ").strip()
        if p:
            out.append(p)
    return out


def split_sentences(text: str, lang: str) -> list[str]:
    if lang.startswith("zh"):
        return _split_sentences_cjk(text)
    return _split_sentences_latin(text)


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------


@dataclass
class ModelPair:
    name: str          # e.g. "en_de"
    src: str           # e.g. "en"
    tgt: str           # e.g. "de"
    path: Path         # .argosmodel file
    extracted: Path | None = None
    version: str = ""


class _LoadedModel:
    __slots__ = ("spm", "translator")

    def __init__(self, model_dir: Path, spm_path: Path):
        self.translator = ctranslate2.Translator(str(model_dir))
        self.spm = sentencepiece.SentencePieceProcessor()
        self.spm.load(str(spm_path))


def _find_extracted(pair: ModelPair) -> Path:
    """Extract the .argosmodel zip if needed and locate the model directory."""
    if pair.extracted is not None:
        return pair.extracted
    target = EXTRACTED_DIR / pair.name
    marker = target / ".extracted_ok"
    if not marker.exists():
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(pair.path) as z:
            z.extractall(target)
        # The zip contains a single top-level dir (e.g. en_de/...)
        inner = [p for p in target.iterdir() if p.is_dir() and p.name != "__MACOSX"]
        if len(inner) == 1:
            pair.extracted = inner[0]
        else:  # flat layout
            pair.extracted = target
        marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        inner = [p for p in target.iterdir() if p.is_dir() and (p / "model").is_dir()]
        pair.extracted = inner[0] if len(inner) == 1 else target
    return pair.extracted


class NMT:
    """Offline neural MT with lazy model loading and a small LRU cache."""

    MAX_CACHED = 2
    MAX_BATCH_TOKENS = 450

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = Path(models_dir)
        self.pairs: dict[str, ModelPair] = {}
        self._cache: OrderedDict[str, _LoadedModel] = OrderedDict()
        self._lock = threading.Lock()
        self._discover()

    # -- registry -----------------------------------------------------------

    def _discover(self) -> None:
        if not self.models_dir.exists():
            return
        for f in sorted(self.models_dir.glob("*.argosmodel")):
            try:
                with zipfile.ZipFile(f) as z:
                    meta_name = next(
                        (n for n in z.namelist() if n.endswith("metadata.json")), None
                    )
                    if meta_name is None:
                        continue
                    meta = json.loads(z.read(meta_name))
            except Exception:
                continue
            src, tgt = meta.get("from_code"), meta.get("to_code")
            if not src or not tgt:
                continue
            self.pairs[f"{src}_{tgt}"] = ModelPair(
                name=f"{src}_{tgt}",
                src=src,
                tgt=tgt,
                path=f,
                version=str(meta.get("package_version", "")),
            )

    @property
    def available_pairs(self) -> list[tuple[str, str]]:
        return [(p.src, p.tgt) for p in self.pairs.values()]

    def route(self, src: str, tgt: str) -> list[tuple[str, str]]:
        """Return the chain of model pairs needed, or [] if impossible."""
        src, tgt = src.lower(), tgt.lower()
        if src == tgt:
            return []
        if f"{src}_{tgt}" in self.pairs:
            return [(src, tgt)]
        if f"{src}_en" in self.pairs and f"en_{tgt}" in self.pairs:
            return [(src, "en"), ("en", tgt)]
        return []

    # -- model loading -------------------------------------------------------

    def _get(self, src: str, tgt: str) -> _LoadedModel:
        with self._lock:
            key = f"{src}_{tgt}"
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            pair = self.pairs[key]
            d = _find_extracted(pair)
            model_dir = d / "model"
            spm_candidates = [
                d / "sentencepiece.model",
                d / "spm",
                d / "src.spm",
                model_dir / "sentencepiece.model",
            ]
            spm_path = next((p for p in spm_candidates if p.exists()), None)
            if spm_path is None:
                raise FileNotFoundError(f"sentencepiece model not found for {key}")
            loaded = _LoadedModel(model_dir, spm_path)
            self._cache[key] = loaded
            while len(self._cache) > self.MAX_CACHED:
                self._cache.popitem(last=False)
            return loaded

    # -- translation ---------------------------------------------------------

    def _translate_chunk_batch(
        self,
        src: str,
        tgt: str,
        chunks: list[str],
        on_chunk: Callable[[int, int, str, str], None] | None = None,
    ) -> list[str]:
        model = self._get(src, tgt)
        out: list[str] = [""] * len(chunks)
        # Group chunks into batches with a token budget.
        batches: list[list[tuple[int, list[str]]]] = []
        cur: list[tuple[int, list[str]]] = []
        cur_tokens = 0
        for i, c in enumerate(chunks):
            toks = model.spm.encode(c, out_type=str)
            if cur and cur_tokens + len(toks) > self.MAX_BATCH_TOKENS:
                batches.append(cur)
                cur, cur_tokens = [], 0
            cur.append((i, toks))
            cur_tokens += len(toks)
        if cur:
            batches.append(cur)

        for batch in batches:
            results = model.translator.translate_batch(
                [toks for _, toks in batch]
            )
            for (i, _), res in zip(batch, results):
                hyp = res.hypotheses[0]
                # ctranslate2 4.x returns plain token lists
                out[i] = model.spm.decode(hyp)
                if on_chunk:
                    on_chunk(i, len(chunks), chunks[i], out[i])
        return out

    def translate_text(
        self,
        src: str,
        tgt: str,
        text: str,
        on_sentence: Callable[[int, int, str, str], None] | None = None,
    ) -> str:
        text = text.strip()
        if not text:
            return ""
        chain = self.route(src, tgt)
        if not chain:
            raise ValueError(f"No translation path from {src} to {tgt}")
        if src == tgt:
            return text
        current = text
        for step_src, step_tgt in chain:
            chunks = split_sentences(current, step_src)
            current = " ".join(
                self._translate_chunk_batch(
                    step_src, step_tgt, chunks, on_sentence
                )
            )
        return current.strip()

    def stats(self) -> dict:
        return {
            "models_available": len(self.pairs),
            "pairs": sorted(
                (p.src, p.tgt) for p in self.pairs.values()
            ),
            "cached": [k for k in self._cache.keys()],
        }


_engine: NMT | None = None
_engine_lock = threading.Lock()


def get_engine() -> NMT:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = NMT()
        return _engine
