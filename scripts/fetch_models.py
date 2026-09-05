#!/usr/bin/env python3
"""Download the offline translation models.

Models (Opus-MT trained, Argos packaging) come from the official
LibreTranslate GitHub mirror:
    https://github.com/LibreTranslate/LibreTranslate-Models

The script does a partial (blob-less) sparse clone so only the
*.argosmodel files are fetched (~1.4 GB, 16 pairs, 9 languages):

    ar, de, en, es, fr, it, pt, ru, zh

Usage:
    python scripts/fetch_models.py [model-name ...]
        # no args → fetch all 16 pairs
        # otherwise only the given pairs, e.g.:
    python scripts/fetch_models.py en_de de_en en_fr
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/LibreTranslate/LibreTranslate-Models.git"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

ALL_MODELS = [
    "ar_en", "de_en",
    "en_ar", "en_de", "en_es", "en_fr", "en_it", "en_pt", "en_ru", "en_zh",
    "es_en", "fr_en", "it_en", "pt_en", "ru_en", "zh_en",
]


def main() -> None:
    wanted = [m.strip().replace(".argosmodel", "") for m in sys.argv[1:]] or ALL_MODELS
    missing = [m for m in wanted if not (MODELS_DIR / f"{m}.argosmodel").exists()]
    have = [m for m in wanted if (MODELS_DIR / f"{m}.argosmodel").exists()]
    if have:
        print(f"Already present: {', '.join(have)}")
    if not missing:
        print("Nothing to download.")
        return
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching: {', '.join(missing)}")
    print("(partial clone from GitHub, ~85 MB per model — this can take a "
          "minute or two)\n")
    with tempfile.TemporaryDirectory(prefix="ltm-") as td:
        repo = Path(td) / "repo"
        subprocess.run(
            [
                "git", "clone", "--filter=blob:none", "--no-checkout",
                "--depth", "1", REPO, str(repo),
            ],
            check=True,
        )
        # sparse checkout of the requested files
        subprocess.run(
            ["git", "sparse-checkout", "set", *missing],
            cwd=repo, check=True,
        )
        subprocess.run(["git", "checkout"], cwd=repo, check=True)
        for m in missing:
            src = repo / f"{m}.argosmodel"
            if not src.exists():
                print(f"  ! {m}.argosmodel not found in repo — skipped")
                continue
            dst = MODELS_DIR / f"{m}.argosmodel"
            dst.write_bytes(src.read_bytes())
            print(f"  ✓ {m}.argosmodel ({dst.stat().st_size / 1e6:.0f} MB)")
    print(f"\nDone. Models in {MODELS_DIR}")


if __name__ == "__main__":
    main()
