"""SAM 3.1: every match of a short noun phrase in an image, as a box and a
full-size mask.

    from pipeline.meta import sam
    for m in sam.segment(photo, "perfume bottle"):
        m.box, m.mask   # (x0, y0, x1, y1) in pixels; a PIL "L" image the photo's size, 255 inside

SAM answers in a text format (dev.meta.ai/docs/sam/reading-segmentation):
per match a box in source pixels and a mask raster covering that box --
for large boxes at a lower resolution (at most 1024 a side), so it's scaled
up to the box here.
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
    raster = Image.frombytes("L", (m.width, m.height), bytes(v * 255 for v in decode_mask_to_raster(m)))
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
        try:
            stored = {"text": _raw_output(image, prompt)}
        except config.MissingKey:
            raise   # not a model failure: say which key to set
        except Exception as e:   # noqa: BLE001
            raise client.wrap_error(config.SAM, e) from e
        cache.put_json(key, stored)
    usage.record(usage.Call(kind="segment", model=config.SAM, cached=cached,
                            seconds=round(time.perf_counter() - began, 3), units=1,
                            cost=0.0 if cached else config.SAM_IMAGE_PRICE))

    text = stored["text"]
    parser = image_segmentation_format().create_parser()
    parser.push(text if not text or text.endswith("\n") else text + "\n")
    records = parser.finish(CompletedOutcome()).result.records
    size = Image.open(io.BytesIO(data)).size
    masks = []
    for r in records:
        if r.kind != "mask":
            continue
        b = r.bounds
        masks.append(Mask(object_id=r.object_id, box=(b.left, b.top, b.right, b.bottom),
                          mask=_full_mask(r, size), confidence=r.confidence))
    return masks
