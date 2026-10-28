"""The HTTP side shared by every model: clients for the Meta Model API and
Baseten (OpenAI-compatible), retries, readable errors, and images as inputs."""

import base64
import mimetypes
from functools import cache as memoize
from pathlib import Path

import openai
from openai import OpenAI

from . import cache, config

# Retries with backoff for rate limits (429) and transient failures (5xx,
# timeouts); the openai client does the waiting.
MAX_RETRIES = 4
TIMEOUT_SECONDS = 180


class MetaError(Exception):
    """A model call that failed after retries, with what to fix."""

    def __init__(self, model: str, message: str, status: int | None = None):
        super().__init__(f"{model}: {message}" + (f" (HTTP {status})" if status else ""))
        self.model, self.message, self.status = model, message, status


@memoize
def meta() -> OpenAI:
    return OpenAI(base_url=config.META_BASE_URL, api_key=config.key("MODEL_API_KEY"),
                  max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS)


@memoize
def baseten() -> OpenAI:
    return OpenAI(base_url=config.BASETEN_BASE_URL, api_key=config.key("BASETEN_API_KEY"),
                  max_retries=MAX_RETRIES, timeout=TIMEOUT_SECONDS)


def wrap_error(model: str, error: Exception) -> MetaError:
    """An openai exception as a MetaError, keeping the server's own message."""
    if isinstance(error, openai.APIStatusError):
        body = error.body if isinstance(error.body, dict) else {}
        detail = body.get("error", body) if isinstance(body, dict) else body
        message = detail.get("message") if isinstance(detail, dict) else None
        return MetaError(model, message or str(error), error.status_code)
    if isinstance(error, openai.APIConnectionError):
        return MetaError(model, f"couldn't reach the API: {error}")
    return MetaError(model, str(error))


# --- Images as inputs --------------------------------------------------------------------

ImageInput = Path | str | bytes


def image_bytes(image: ImageInput) -> tuple[bytes, str]:
    """An image's bytes and MIME type, from a path or raw PNG/JPEG bytes."""
    if isinstance(image, bytes):
        mime = "image/png" if image[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        return image, mime
    path = Path(image)
    return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/png"


def data_url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def image_keys(images: list[ImageInput]) -> list[str]:
    """What identifies the images in a cache key: their bytes' hashes."""
    return [cache.digest(image_bytes(i)[0]) for i in images]
