"""Shared setup for the smoke tests: the repo on the import path, the output
folder (pipeline/meta/smoke/out, git-ignored), and Skip for tests that
can't run here. The calls themselves go through pipeline.meta."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

# 03 generates it; 04, 05 and 07 read it.
PRODUCT_PHOTO = OUT / "product.png"


class Skip(Exception):
    """The test can't run here (an earlier test's output is missing)."""


def product_photo() -> Path:
    if not PRODUCT_PHOTO.exists():
        raise Skip(f"no {PRODUCT_PHOTO.name} yet: run 03_image_generate.py first")
    return PRODUCT_PHOTO


def report(result: dict) -> None:
    """Prints a test's result when it's run on its own."""
    for k, v in result.items():
        print(f"{k}: {v}")
