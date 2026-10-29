"""Muse Image: a picture from a prompt, saved as PNG.

    from pipeline.meta import image
    path = image.generate("seamless black velvet texture, soft folds", size="1024x1024", out=run / "velvet.png")

`size` sets the aspect ratio, not exact pixels: 1024x1536 comes back 1280x1920.
"""

import base64
import shutil
import time
from pathlib import Path

from . import cache, client, config, usage


def generate(prompt: str, *, size: str = "1024x1024", out: Path | None = None, cache_ok: bool = True) -> Path:
    """Generates an image for `prompt` and returns its PNG path: `out` if
    given, else the cached file itself."""
    key = cache.request_key("image.generate", {"model": config.IMAGE, "prompt": prompt, "size": size})
    began = time.perf_counter()
    png = cache.get_bytes(key, ".png", cache_ok)
    cached = png is not None
    if not cached:
        result = client.call(config.IMAGE, lambda: client.meta().images.generate(
            model=config.IMAGE, prompt=prompt, size=size, extra_body={"output_format": "png"}))
        png = base64.b64decode(result.data[0].b64_json)
    stored = cache.put_bytes(key, ".png", png) if not cached else cache.path(key, ".png")
    usage.record(usage.Call(kind="image", model=config.IMAGE, cached=cached,
                            seconds=round(time.perf_counter() - began, 3), units=1,
                            cost=0.0 if cached else config.IMAGE_PRICE))
    if out is None:
        return stored
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stored, out)
    return out
