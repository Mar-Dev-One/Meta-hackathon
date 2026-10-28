"""A disk cache for model calls: the same request returns the stored answer
instead of calling (and paying for) the model again. A request is keyed by
a hash of everything that shapes the answer -- model, inputs, images by
their bytes -- so a changed prompt or image is a new request.

Turn it off for a run with META_CACHE=off, or per call with cache=False.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from . import config


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_key(kind: str, request: Any) -> str:
    """A stable key for a request (dicts in any key order give the same key)."""
    text = json.dumps({"kind": kind, "request": request}, sort_keys=True, separators=(",", ":"), default=str)
    return digest(text.encode("utf-8"))


def path(key: str, suffix: str) -> Path:
    """Where a cached answer lives (whether or not it's there yet)."""
    return config.CACHE_DIR / key[:2] / f"{key}{suffix}"


def get_json(key: str, enabled: bool = True) -> Any | None:
    file = path(key, ".json")
    if not (enabled and config.CACHE_ENABLED and file.exists()):
        return None
    return json.loads(file.read_text(encoding="utf-8"))


def put_json(key: str, value: Any) -> None:
    file = path(key, ".json")
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, default=str), encoding="utf-8")


def get_bytes(key: str, suffix: str, enabled: bool = True) -> bytes | None:
    file = path(key, suffix)
    if not (enabled and config.CACHE_ENABLED and file.exists()):
        return None
    return file.read_bytes()


def put_bytes(key: str, suffix: str, data: bytes) -> Path:
    file = path(key, suffix)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(data)
    return file
