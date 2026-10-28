"""Models, endpoints, keys and prices for the Meta models (dev.meta.ai/docs,
pricing as listed on 2026-10-28)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

META_BASE_URL = "https://api.meta.ai/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"

SPARK = "muse-spark-1.3"
SPARK_CONTRIBUTOR = "muse-spark-1.3-contributor"   # contributor mode: far cheaper; see the pricing docs for its terms
IMAGE = "muse-image-1.0"
SAM = "sam-3.1"
VOICE = "muse-voice-transcribe-1.0"
SPARK_OPEN = "meta-models/muse-spark-open-1026"   # on Baseten (the hackathon's name, not the one in their docs)

# Dollars. Text models: per million tokens (input, cached input, output).
TOKEN_PRICES = {
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.2-contributor": (0.10, 0.002, 0.20),
    "muse-spark-1.1": (1.25, 0.15, 4.25),
}
IMAGE_PRICE = 0.01            # per generated image
SAM_IMAGE_PRICE = 2.50 / 1000  # per image segmented
VOICE_PRICE_PER_SECOND = 0.18 / 3600

# Where answers are kept so the same request never costs twice (git-ignored).
CACHE_DIR = Path(os.environ.get("META_CACHE_DIR", ROOT / "cache" / "meta"))
CACHE_ENABLED = os.environ.get("META_CACHE", "on").lower() not in ("0", "off", "false", "no")


class MissingKey(Exception):
    pass


def key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingKey(f"{name} isn't set: add it to {ROOT / '.env'} (see .env.example)")
    return value
