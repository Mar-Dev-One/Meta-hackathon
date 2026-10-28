"""A round product's 3D shape from its photo: the product mask's half-width
per row, about its vertical axis, is the profile the Studio spins into a
model (product.create with "parts"). SAM's mask becomes the shape.

    seg = segment(photo, "olive oil bottle")
    traced = trace(seg, height=typical_height("olive oil bottle"))
    traced.parts        # [ProfilePart body, ProfilePart cap], meters, bottom to top
    outline(seg, traced).save("profile.png")    # the profile drawn back over the photo

The widths are median-filtered (a row of stray pixels doesn't make a ridge)
and simplified to the fewest points within a pixel or two of the mask, so
straight sides stay straight and shoulders stay sharp. The cap's lowest row
splits the product into body and cap. Assumes a front view, upright, at
about eye level: what's seen of the top and bottom faces adds a little height.

    python -m pipeline.agents.analyst.profile Assets/photos/solana_oil.png --category "olive oil bottle"
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from pipeline.schemas.storyboard import ProfilePart

from .segment import Segmentation

# Typical real heights (meters) by a word in the category, first match wins.
HEIGHTS = [("perfume", 0.12), ("dropper", 0.11), ("serum", 0.11), ("jar", 0.07), ("can", 0.122),
           ("oil", 0.28), ("wine", 0.30), ("bottle", 0.25)]
DEFAULT_HEIGHT = 0.15

MAX_POINTS = 60          # per part; the Studio takes 64
TOLERANCE = 0.0025       # simplified profile stays this share of the height from the mask (at least 1 px)


@dataclass
class Traced:
    parts: list[ProfilePart]                          # meters, bottom to top, closed on the axis
    pixels: dict[str, list[tuple[float, float]]]      # the same profiles in photo pixels: (half-width, up from the bottom)
    axis: float                                       # the photo column of the product's axis
    bottom: int                                       # the photo row just below the product
    height: float                                     # meters
    meters_per_pixel: float
    top: int = 0                                      # the photo row of the product's top
    radii: np.ndarray | None = None                   # the smoothed half-width of each row from `top`, pixels

    def radius_at(self, row: int) -> float:
        """The product's half-width at a photo row, pixels."""
        return float(self.radii[min(max(row - self.top, 0), len(self.radii) - 1)])


def typical_height(category: str) -> float:
    category = category.lower()
    return next((h for word, h in HEIGHTS if word in category), DEFAULT_HEIGHT)


def _rows(mask: Image.Image) -> tuple[int, int, np.ndarray, np.ndarray]:
    """The mask's top and bottom (exclusive) rows, and each row's half-width
    and centre between them; gaps filled from their neighbours."""
    m = np.asarray(mask) > 127
    filled = np.nonzero(m.any(axis=1))[0]
    top, bottom = int(filled[0]), int(filled[-1]) + 1
    m = m[top:bottom]
    has = m.any(axis=1)
    left = m.argmax(axis=1).astype(float)
    right = (m.shape[1] - 1 - m[:, ::-1].argmax(axis=1)).astype(float)
    half, center = (right - left + 1) / 2, (left + right + 1) / 2
    rows = np.arange(len(m))
    half = np.interp(rows, rows[has], half[has])
    center = np.interp(rows, rows[has], center[has])
    return top, bottom, half, center


def _median(values: np.ndarray, window: int) -> np.ndarray:
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(padded, window), axis=1)


def _simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas-Peucker: the fewest points whose polyline stays within
    `tolerance` of `points` (first and last kept)."""
    keep = np.zeros(len(points), bool)
    keep[[0, -1]] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = points[i], points[j]
        d = b - a
        seg = points[i + 1:j] - a
        dist = np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / max(np.hypot(*d), 1e-9)
        k = int(dist.argmax())
        if dist[k] > tolerance:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return points[keep]


def _profile(half: np.ndarray, lo: int, hi: int, height_px: int, tolerance: float) -> list[tuple[float, float]]:
    """Rows lo..hi (indices from the top) as a profile from the bottom up,
    closed on the axis."""
    rows = np.arange(hi - 1, lo - 1, -1)                 # bottom row first
    up = height_px - rows - 0.5                          # each row's centre, up from the bottom
    radii = half[rows]
    side = np.column_stack([np.r_[radii[0], radii, radii[-1]], np.r_[height_px - hi, up, height_px - lo]])
    while True:
        simple = _simplify(side, tolerance)
        if len(simple) <= MAX_POINTS - 2:
            break
        tolerance *= 1.5
    floor, ceiling = height_px - hi, height_px - lo
    return [(0.0, floor), *map(tuple, simple), (0.0, ceiling)]


def _color(image: Image.Image, mask: np.ndarray) -> str:
    """The median colour under a mask (a stand-in until the palette and
    materials steps)."""
    pixels = np.asarray(image)[mask]
    r, g, b = np.median(pixels, axis=0).astype(int) if len(pixels) else (128, 128, 128)
    return f"#{r:02X}{g:02X}{b:02X}"


def trace(seg: Segmentation, height: float) -> Traced:
    """The product's profile from its mask, scaled to `height` meters, split
    into body and cap at the cap's lowest row (just a body without a cap)."""
    top, bottom, half, center = _rows(seg.product.mask)
    height_px = bottom - top
    half = _median(half, max(3, height_px // 100) | 1)
    axis = float(np.median(center))
    tolerance = max(1.0, TOLERANCE * height_px)

    cap = seg.parts.get("cap")
    split = height_px if cap is None else min(max(cap.box[3] - top, 1), height_px - 1)
    pieces = [("body", split, height_px)] + ([("cap", 0, split)] if cap else [])

    product = np.asarray(seg.product.mask) > 127
    label = np.asarray(seg.parts["label"].mask) > 127 if "label" in seg.parts else np.zeros_like(product)
    scale = height / height_px
    parts, pixels = [], {}
    for name, lo, hi in pieces:
        profile = _profile(half, lo, hi, height_px, tolerance)
        pixels[name] = profile
        under = product.copy()
        under[: top + lo] = False
        under[top + hi:] = False
        if name == "body":
            under &= ~label
        parts.append(ProfilePart(name=name, profile=[[round(r * scale, 5), round(y * scale, 5)] for r, y in profile],
                                 color=_color(seg.image, under), roughness=0.3))
    return Traced(parts, pixels, axis, bottom, height, scale, top, half)


def outline(seg: Segmentation, traced: Traced) -> Image.Image:
    """The photo with each part's profile drawn on both sides of the axis."""
    out = seg.image.copy()
    draw = ImageDraw.Draw(out)
    colors = {"body": (255, 70, 70), "cap": (70, 150, 255)}
    width = max(3, out.height // 250)
    dot = 2 * width
    for name, profile in traced.pixels.items():
        for side in (-1, 1):
            line = [(traced.axis + side * r, traced.bottom - y) for r, y in profile]
            draw.line(line, fill=colors.get(name, (255, 255, 0)), width=width)
            for x, y in line[1:-1]:
                draw.ellipse([x - dot, y - dot, x + dot, y + dot], outline=(255, 255, 255), width=width // 2 + 1)
    draw.line([(traced.axis, traced.bottom), (traced.axis, traced.bottom - traced.height / traced.meters_per_pixel)],
              fill=(255, 255, 255), width=1)
    return out


async def render(studio, traced: Traced, out_dir, label: dict | None = None, width: int = 640,
                 height: int = 960) -> tuple[str, dict]:
    """The traced product (with `label`, product.create's label argument)
    alone on a light set, seen from the front at eye level as in a product
    photo; the frame's path and the product's box in it."""
    await studio.call("studio.reset")
    await studio.call("environment.set", ambient_strength=0.6, bloom=0.03, tonemap="neutral")
    await studio.call("render.set", antialiasing="taa", clear_color=[0.78, 0.78, 0.78])
    await studio.call("backdrop.create", kind="cyclorama", color="#D6D6D6", roughness=0.9)
    await studio.call("product.create", name="product", position=[0, 0, 0],
                      parts=[p.model_dump(exclude_none=True) for p in traced.parts], **({"label": label} if label else {}))
    await studio.call("lighting.preset", subject="product", name="high_key")
    await studio.call("camera.move", move="static", subject="product", start=0, duration=1, fill=0.75,
                      elevation=4, fov_degrees=20, aspect=width / height)
    frame = await studio.call("shot.preview", times=[0.5], width=width, height=height, out_dir=str(out_dir))
    bounds = await studio.call("shot.bounds", entity="product", t=0.5, width=width, height=height)
    return frame["frames"][0]["path"], bounds


def side_by_side(seg: Segmentation, frame: Image.Image, bounds: dict, height: int = 900) -> Image.Image:
    """The photo and the render, each cut to its product (with a margin) and
    scaled to the same height."""
    def crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
        x0, y0, x1, y1 = box
        margin = 0.12 * (y1 - y0)
        cx, half_w = (x0 + x1) / 2, max((x1 - x0) / 2, (y1 - y0) * 0.3) + margin
        tile = image.crop((round(cx - half_w), round(y0 - margin), round(cx + half_w), round(y1 + margin)))
        return tile.resize((round(tile.width * height / tile.height), height), Image.Resampling.LANCZOS)

    w, h = frame.size
    b = bounds["box"]
    photo = crop(seg.image, seg.product.box)
    render_ = crop(frame.convert("RGB"), (b[0] * w, b[1] * h, b[2] * w, b[3] * h))
    out = Image.new("RGB", (photo.width + render_.width + 12, height), (255, 255, 255))
    out.paste(photo, (0, 0))
    out.paste(render_, (photo.width + 12, 0))
    return out


if __name__ == "__main__":
    import argparse
    import asyncio
    from pathlib import Path

    from pipeline.runs import Run
    from pipeline.studio import Studio

    from .label import unroll
    from .palette import palette, strip
    from .segment import segment

    parser = argparse.ArgumentParser(description="Trace a product photo into a 3D product with its label, rendered "
                                                 "next to the photo; and its palette.")
    parser.add_argument("photos", nargs="+")
    parser.add_argument("--category", action="append", help="per photo, in order (default: product)")
    args = parser.parse_args()
    categories = (args.category or []) + ["product"] * len(args.photos)

    async def main() -> None:
        async with Studio() as studio:
            for photo, category in zip(args.photos, categories):
                with Run.create(f"profile-{Path(photo).stem}") as run:
                    run.watch(studio)
                    run.add_file(photo, "inputs/" + Path(photo).name)
                    seg = segment(photo, category)
                    traced = trace(seg, typical_height(category))
                    run.save_json("profile.json", {"height": traced.height, "parts": [
                        p.model_dump(exclude_none=True) for p in traced.parts]})
                    outline(seg, traced).save(run.path("outline.png"))
                    cut = unroll(seg, traced)
                    label = None
                    if cut:
                        cut.image.save(run.path("label.png"))
                        label = cut.command(str(run.root / "label.png"))
                        run.event("label", **label, size=cut.image.size)
                    swatches = palette(seg)
                    run.save_json("palette.json", [s.model_dump() for s in swatches])
                    path, bounds = await render(studio, traced, run.folder("frames"), label)
                    compare = side_by_side(seg, Image.open(path), bounds)
                    colours = strip(swatches, compare.width)
                    sheet = Image.new("RGB", (compare.width, compare.height + colours.height), (255, 255, 255))
                    sheet.paste(compare, (0, 0))
                    sheet.paste(colours, (0, compare.height))
                    sheet.save(run.path("compare.png"))
                    run.output("compare", run.root / "compare.png")
                    print(run.root, [len(p.profile) for p in traced.parts], "points")

    asyncio.run(main())
