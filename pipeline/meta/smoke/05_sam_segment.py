"""SAM 3.1 on the product photo: the whole product, then its parts. Saves an
overlay of the masks, and tries the silhouette-to-profile idea (the product
mask's half-width per row is the lathe profile of a round product).

Output format (dev.meta.ai/docs/sam/reading-segmentation): text records, a box
in source pixels and a mask raster the size of that box; decoded with the
meta-sam-parser package."""

from PIL import Image

from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

from _common import OUT, SAM, data_url, meta_client, product_photo, report, save_json, timed

PROMPTS = ["perfume bottle", "bottle cap", "label"]
COLORS = [(255, 64, 64), (64, 160, 255), (64, 220, 120)]


def segment(client, photo_url: str, prompt: str) -> tuple[str, list]:
    """SAM's raw output text and its (box, mask raster) pairs."""
    chunks = []
    with client.responses.stream(
        model=SAM,
        input=[{
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": photo_url}],
        }],
    ) as stream:
        for event in stream:
            if event.type == "response.output_text.delta":
                chunks.append(event.delta)
    text = "".join(chunks)

    parser = image_segmentation_format().create_parser()
    parser.push(text if text.endswith("\n") or not text else text + "\n")
    result = parser.finish(CompletedOutcome()).result
    masks = [r for r in result.records if r.kind == "mask"]
    return text, masks


def full_mask(record, size: tuple[int, int]) -> Image.Image:
    """A frame-sized 0/255 mask from a record's raster. The raster covers the
    record's box, but large ones come at a lower resolution (at most 1024 a
    side), so it's scaled up to the box first."""
    m, b = record.mask, record.bounds
    raster = Image.frombytes("L", (m.width, m.height), bytes(v * 255 for v in decode_mask_to_raster(m)))
    box_size = (b.right - b.left, b.bottom - b.top)
    if raster.size != box_size:
        raster = raster.resize(box_size, Image.Resampling.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
    out = Image.new("L", size, 0)
    out.paste(raster, (b.left, b.top))
    return out


def profile(mask: Image.Image) -> list[tuple[int, float]]:
    """(height, half-width) in px, from the product's bottom row up: the lathe profile in pixels."""
    left, top, right, bottom = mask.getbbox()
    px = mask.load()
    rows = []
    for y in range(bottom - 1, top - 1, -1):
        xs = [x for x in range(left, right) if px[x, y]]
        if xs:
            rows.append((bottom - 1 - y, (xs[-1] - xs[0] + 1) / 2))
    return rows


def run() -> dict:
    client = meta_client()
    photo = product_photo()
    url = data_url(photo)
    image = Image.open(photo).convert("RGB")

    found, raw, latencies = {}, {}, {}
    overlay = image.copy()
    for prompt, color in zip(PROMPTS, COLORS):
        with timed() as t:
            text, masks = segment(client, url, prompt)
        latencies[prompt] = t.seconds
        raw[prompt] = text
        found[prompt] = len(masks)
        for record in masks:
            mask = full_mask(record, image.size)
            overlay = Image.composite(Image.blend(overlay, Image.new("RGB", image.size, color), 0.5), overlay, mask)
            if prompt == PROMPTS[0] and record is masks[0]:
                mask.save(OUT / "05_product_mask.png")
                rows = profile(mask)
                (OUT / "05_profile_px.csv").write_text(
                    "height_px,half_width_px\n" + "".join(f"{y},{r}\n" for y, r in rows), encoding="utf-8")

    overlay.save(OUT / "05_sam_overlay.png")
    save_json("05_sam_raw.json", raw)
    result = {"latency_s": latencies, "matches": found, "overlay": str(OUT / "05_sam_overlay.png")}
    if (OUT / "05_profile_px.csv").exists():
        lines = (OUT / "05_profile_px.csv").read_text().splitlines()[1:]
        widths = [float(l.split(",")[1]) for l in lines]
        result["profile"] = f"{len(lines)} rows, half-width {min(widths):.0f}-{max(widths):.0f} px (05_profile_px.csv)"
    return result


if __name__ == "__main__":
    report(run())
