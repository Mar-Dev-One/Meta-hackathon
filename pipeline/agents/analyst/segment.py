"""The product and its parts in a photo, from SAM 3.1.

    seg = segment(photo, "perfume bottle")
    seg.product.mask             # "L", the photo's size: 255 on the product
    seg.parts["cap"].box         # (left, top, right, bottom) in pixels, if a cap was found
    overlay(seg).save("masks.png")

The product is the largest match of its category (or of "product"). A part
is the largest match of one of its phrases that lies on the product, cut to
the product's mask: SAM also finds the caps and labels of things in the
background, and a part's edge can spill past the product's.

    python -m pipeline.agents.analyst.segment Assets/photos/solana_oil.png --category "olive oil bottle"
"""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from pipeline.meta import sam

# Each part: the phrases tried, in order, until one finds it on the product.
PARTS: dict[str, list[str]] = {"cap": ["cap", "lid"], "label": ["label"]}

ON_PRODUCT = 0.6    # a part's share that must lie on the product's mask
WHOLE = 0.9         # a "part" this big a share of the product is the product itself

COLORS = {"product": (255, 70, 70), "cap": (70, 150, 255), "label": (60, 210, 110)}


class NoProduct(Exception):
    """SAM found nothing matching the product in the photo."""


@dataclass
class Region:
    name: str                          # "product", "cap", "label"
    prompt: str                        # the phrase SAM found it with
    mask: Image.Image                  # "L", the photo's size: 255 inside
    box: tuple[int, int, int, int]     # left, top, right, bottom (exclusive), pixels
    confidence: float | None = None

    @property
    def area(self) -> int:
        return area(self.mask)


@dataclass
class Segmentation:
    photo: Path
    image: Image.Image                 # the photo, RGB
    product: Region
    parts: dict[str, Region] = field(default_factory=dict)


def area(mask: Image.Image) -> int:
    return sum(mask.histogram()[1:])


def _product(photo: Path, category: str) -> Region:
    for prompt in dict.fromkeys([category, "product"]):
        matches = sam.segment(photo, prompt)
        if matches:
            m = max(matches, key=lambda m: m.area)
            return Region("product", prompt, m.mask, m.box, m.confidence)
    raise NoProduct(f"SAM found no {category!r} in {photo}")


def _part(photo: Path, name: str, prompts: list[str], product: Region) -> Region | None:
    for prompt in prompts:
        best = None
        for m in sam.segment(photo, prompt):
            on = ImageChops.multiply(m.mask, product.mask)
            on_area = area(on)
            if not on_area or on_area < ON_PRODUCT * m.area or on_area > WHOLE * product.area:
                continue
            if best is None or on_area > best[0]:
                best = (on_area, on, m.confidence)
        if best:
            _, mask, confidence = best
            return Region(name, prompt, mask, mask.getbbox(), confidence)
    return None


def segment(photo: Path | str, category: str = "product", parts: dict[str, list[str]] | None = None) -> Segmentation:
    """The product (the largest match of `category`) and its parts; a part
    SAM can't find on the product is left out. NoProduct if there's no product."""
    photo = Path(photo)
    product = _product(photo, category)
    found = {}
    for name, prompts in (PARTS if parts is None else parts).items():
        region = _part(photo, name, prompts, product)
        if region:
            found[name] = region
    return Segmentation(photo, Image.open(photo).convert("RGB"), product, found)


def overlay(seg: Segmentation) -> Image.Image:
    """The photo with the background dimmed, the parts tinted, the product
    outlined, and every region's box and name."""
    out = Image.composite(seg.image, Image.blend(seg.image, Image.new("RGB", seg.image.size), 0.6), seg.product.mask)
    for region in seg.parts.values():
        tint = Image.new("RGB", seg.image.size, COLORS.get(region.name, (255, 255, 0)))
        out = Image.composite(Image.blend(out, tint, 0.45), out, region.mask)
    edge = seg.product.mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5))
    out = Image.composite(Image.new("RGB", out.size, COLORS["product"]), out, edge)

    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=max(16, seg.image.height // 50))
    for region in [seg.product, *seg.parts.values()]:
        color = COLORS.get(region.name, (255, 255, 0))
        left, top, right, bottom = region.box
        draw.rectangle([left, top, right - 1, bottom - 1], outline=color, width=3)
        conf = f" {region.confidence:.2f}" if region.confidence is not None else ""
        # The product's name goes under its box: a cap's box shares its top edge.
        y = bottom + 6 if region is seg.product else top + 4
        draw.text((left + 6, y), f"{region.name} ({region.prompt}){conf}", fill=color,
                  font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    return out


if __name__ == "__main__":
    import argparse

    from pipeline.runs import Run

    parser = argparse.ArgumentParser(description="Segment a product photo into a run folder: masks and an overlay.")
    parser.add_argument("photo")
    parser.add_argument("--category", default="product", help='what the product is: "perfume bottle", "jar", ...')
    args = parser.parse_args()

    with Run.create(f"segment-{Path(args.photo).stem}") as run:
        run.add_file(args.photo, "inputs/" + Path(args.photo).name)
        seg = segment(args.photo, args.category)
        for region in [seg.product, *seg.parts.values()]:
            region.mask.save(run.path("masks", f"{region.name}.png"))
            run.event("region", name=region.name, prompt=region.prompt, box=region.box, area=region.area,
                      confidence=region.confidence)
        overlay(seg).save(run.path("masks.png"))
        run.output("overlay", run.root / "masks.png")
    print(run.root / "masks.png")
