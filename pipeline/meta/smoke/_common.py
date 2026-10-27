"""Shared setup for the smoke tests: API keys from the repo's .env, clients,
model IDs, timing and the output folder (pipeline/meta/smoke/out, git-ignored)."""

import base64
import json
import mimetypes
import os
import time
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")

META_BASE_URL = "https://api.meta.ai/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"

SPARK = "muse-spark-1.3"
IMAGE = "muse-image-1.0"
SAM = "sam-3.1"
VOICE = "muse-voice-transcribe-1.0"
SPARK_OPEN = "meta-models/muse-spark-open-1026"   # the hackathon's name on Baseten, not the one in their docs

# 03 generates it; 04, 05 and 07 read it.
PRODUCT_PHOTO = OUT / "product.png"


class Skip(Exception):
    """The test can't run here (no key, or an earlier test's output is missing)."""


def key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise Skip(f"{name} isn't set: add it to {ROOT / '.env'} (see .env.example)")
    return value


def meta_client() -> OpenAI:
    return OpenAI(base_url=META_BASE_URL, api_key=key("MODEL_API_KEY"))


def baseten_client() -> OpenAI:
    return OpenAI(base_url=BASETEN_BASE_URL, api_key=key("BASETEN_API_KEY"))


def product_photo() -> Path:
    if not PRODUCT_PHOTO.exists():
        raise Skip(f"no {PRODUCT_PHOTO.name} yet: run 03_image_generate.py first")
    return PRODUCT_PHOTO


def data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


class Timer:
    seconds: float = 0.0


@contextmanager
def timed():
    timer = Timer()
    start = time.perf_counter()
    try:
        yield timer
    finally:
        timer.seconds = round(time.perf_counter() - start, 2)


def save_json(name: str, data) -> Path:
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def report(result: dict) -> None:
    """Prints a test's result when it's run on its own."""
    for k, v in result.items():
        print(f"{k}: {v}")
