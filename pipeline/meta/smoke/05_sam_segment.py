"""SAM 3.1 on the product photo: the whole product, then its parts, drawn
over the photo; and the silhouette-to-profile idea (the product mask's
half-width per row is the lathe profile of a round product)."""

from PIL import Image

from _common import OUT, product_photo, report

from pipeline.meta import sam

PROMPTS = ["perfume bottle", "bottle cap", "label"]
COLORS = [(255, 64, 64), (64, 160, 255), (64, 220, 120)]


def profile(mask: Image.Image) -> list[tuple[int, float]]:
    """(height, half-width) in px, from the product's bottom row up."""
    left, top, right, bottom = mask.getbbox()
    px = mask.load()
    rows = []
    for y in range(bottom - 1, top - 1, -1):
        xs = [x for x in range(left, right) if px[x, y]]
        if xs:
            rows.append((bottom - 1 - y, (xs[-1] - xs[0] + 1) / 2))
    return rows


def run() -> dict:
    photo = product_photo()
    image = Image.open(photo).convert("RGB")
    overlay, found = image.copy(), {}
    for prompt, color in zip(PROMPTS, COLORS):
        masks = sam.segment(photo, prompt)
        found[prompt] = len(masks)
        for m in masks:
            overlay = Image.composite(Image.blend(overlay, Image.new("RGB", image.size, color), 0.5), overlay, m.mask)
        if prompt == PROMPTS[0] and masks:
            rows = profile(masks[0].mask)
            (OUT / "05_profile_px.csv").write_text("height_px,half_width_px\n" + "".join(f"{y},{r}\n" for y, r in rows),
                                                   encoding="utf-8")
    overlay.save(OUT / "05_sam_overlay.png")
    result = {"matches": found, "overlay": str(OUT / "05_sam_overlay.png")}
    if found.get(PROMPTS[0]):
        widths = [r for _, r in rows]
        result["profile"] = f"{len(rows)} rows, half-width {min(widths):.0f}-{max(widths):.0f} px"
    return result


if __name__ == "__main__":
    report(run())
