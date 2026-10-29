"""SAM 3.1: every match of a short noun phrase in an image, as a box and a
full-size mask.

    from pipeline.meta import sam
    for m in sam.segment(photo, "perfume bottle"):
        m.box, m.mask   # (x0, y0, x1, y1) in pixels; a PIL "L" image the photo's size, 255 inside

SAM answers in a text format (dev.meta.ai/docs/sam/reading-segmentation):
per match a box in source pixels and a mask raster covering that box --
for large boxes at a lower resolution (at most 1024 a side), so it's scaled
up to the box here. Decoding a mask takes seconds (meta_sam_parser is pure
Python), so the decoded masks are cached too, as PNGs of their boxes.
"""

import io
import time
from dataclasses import dataclass

from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
from PIL import Image

from . import cache, client, config, usage
from .client import ImageInput


@dataclass
class Mask:
    object_id: str
    box: tuple[int, int, int, int]   # left, top, right, bottom (exclusive), source pixels
    mask: Image.Image                # "L", the source image's size: 255 inside, 0 outside
    confidence: float | None = None

    @property
    def area(self) -> int:
        return sum(self.mask.histogram()[1:])   # pixels inside


def _full_mask(record, size: tuple[int, int]) -> Image.Image:
    m, b = record.mask, record.bounds
    raster = Image.frombytes("L", (m.width, m.height), decode_mask_to_raster(m)).point(lambda v: v * 255)
    box_size = (b.right - b.left, b.bottom - b.top)
    if raster.size != box_size:
        raster = raster.resize(box_size, Image.Resampling.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
    out = Image.new("L", size, 0)
    out.paste(raster, (b.left, b.top))
    return out


def _raw_output(image: ImageInput, prompt: str) -> str:
    """SAM's answer text for one image and phrase."""
    data, mime = client.image_bytes(image)
    chunks = []
    with client.meta().responses.stream(
        model=config.SAM,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": client.data_url(data, mime)},
        ]}],
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                chunks.append(event.delta)
    return "".join(chunks)


def segment(image: ImageInput, prompt: str, cache_ok: bool = True) -> list[Mask]:
    """Every match of `prompt` (one short noun phrase: "bottle cap") in the
    image, in SAM's order. Empty if nothing matches."""
    data, _ = client.image_bytes(image)
    key = cache.request_key("sam.segment", {"model": config.SAM, "image": cache.digest(data), "prompt": prompt})
    began = time.perf_counter()
    stored = cache.get_json(key, cache_ok)
    cached = stored is not None
    if not cached:
        stored = {"text": client.call(config.SAM, lambda: _raw_output(image, prompt))}
        cache.put_json(key, stored)
    usage.record(usage.Call(kind="segment", model=config.SAM, cached=cached,
                            seconds=round(time.perf_counter() - began, 3), units=1,
                            cost=0.0 if cached else config.SAM_IMAGE_PRICE))

    size = Image.open(io.BytesIO(data)).size
    decoded_key = cache.request_key("sam.decoded", key)
    decoded = cache.get_json(decoded_key, cache_ok and cached)
    if decoded is not None:
        return [_load(decoded_key, i, d, size) for i, d in enumerate(decoded)]

    text = stored["text"]
    parser = image_segmentation_format().create_parser()
    parser.push(text if not text or text.endswith("\n") else text + "\n")
    records = parser.finish(CompletedOutcome()).result.records
    masks = []
    for r in records:
        if r.kind != "mask":
            continue
        b = r.bounds
        masks.append(Mask(object_id=r.object_id, box=(b.left, b.top, b.right, b.bottom),
                          mask=_full_mask(r, size), confidence=r.confidence))
    for i, m in enumerate(masks):
        png = io.BytesIO()
        m.mask.crop(m.box).save(png, "PNG")
        cache.put_bytes(decoded_key, f".{i}.png", png.getvalue())
    cache.put_json(decoded_key, [{"object_id": m.object_id, "box": m.box, "confidence": m.confidence} for m in masks])
    return masks


def _load(key: str, i: int, d: dict, size: tuple[int, int]) -> Mask:
    """A decoded mask from the cache: its box's PNG, placed on the photo."""
    mask = Image.new("L", size, 0)
    mask.paste(Image.open(cache.path(key, f".{i}.png")).convert("L"), tuple(d["box"][:2]))
    return Mask(object_id=d["object_id"], box=tuple(d["box"]), mask=mask, confidence=d["confidence"])
