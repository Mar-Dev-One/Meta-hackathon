"""The label cut from the photo and unrolled, to wrap round the 3D body.

    cut = unroll(seg, traced)
    cut.image.save("label.png")       # RGBA, flat: as printed, before it went round the bottle
    {"image": "label.png", "part": "body", "from": cut.from_, "to": cut.to, "arc": cut.arc}   # product.create's label

On a round body a point at angle a from the front shows at x = axis + r sin a,
so the photo squeezes a label towards the sides. Unrolling samples the photo
at those x for evenly spaced angles, row by row with that row's radius: the
inverse of the Studio's wrap. Past MAX_ANGLE the side is too foreshortened
to read, so a label that runs round the back is cut there. The light on the
photo (darker towards the sides) is divided out using the label's paper,
its brightest pixels down each column, so the Studio's lights don't add
theirs to it.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .profile import Traced, _median
from .segment import Segmentation

MAX_ANGLE = np.radians(72)
MAX_GAIN = 1.8      # the most a column is brightened to undo the shading


@dataclass
class CutLabel:
    image: Image.Image     # RGBA, unrolled
    from_: float           # meters up the product where it starts
    to: float              # where it ends
    arc: float             # degrees it covers round the body
    part: str = "body"

    def command(self, path: str) -> dict:
        """product.create's "label" argument, with the image saved at `path`."""
        return {"image": path, "part": self.part, "from": round(self.from_, 5), "to": round(self.to, 5),
                "arc": round(self.arc, 2)}


def _sample(image: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear samples of an H x W x C array at pixel positions (x, y)."""
    h, w = image.shape[:2]
    x = np.clip(x - 0.5, 0, w - 1.001)
    y = np.clip(y - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    a, b = image[y0, x0], image[y0, x0 + 1]
    c, d = image[y0 + 1, x0], image[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _flatten(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Divides out the light falling across the label: each column's paper
    brightness (a high percentile, smoothed across columns) is lifted to
    the brightest column's."""
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    inside = alpha > 0.5
    paper = np.array([np.percentile(col[m], 85) if m.sum() > 8 else np.nan for col, m in zip(luma.T, inside.T)])
    if np.isnan(paper).all():
        return rgb
    columns = np.arange(len(paper))
    good = ~np.isnan(paper)
    paper = np.interp(columns, columns[good], paper[good])
    paper = _median(paper, max(3, len(paper) // 15) | 1)
    gain = np.clip(np.percentile(paper, 95) / np.maximum(paper, 1), 1.0, MAX_GAIN)
    return np.clip(rgb * gain[None, :, None], 0, 255)


def unroll(seg: Segmentation, traced: Traced, flatten: bool = True) -> CutLabel | None:
    """The label as printed (None if the photo has no label)."""
    region = seg.parts.get("label")
    if region is None:
        return None
    mask = np.asarray(region.mask) > 127
    rows = np.nonzero(mask.any(axis=1))[0]
    top, bottom = int(rows[0]), int(rows[-1]) + 1

    # Its angles round the body: the median over its rows of where its edges are.
    lefts, rights = [], []
    for y in rows:
        xs = np.nonzero(mask[y])[0]
        r = max(traced.radius_at(y), 1.0)
        lefts.append(np.arcsin(np.clip((xs[0] - traced.axis) / r, -1, 1)))
        rights.append(np.arcsin(np.clip((xs[-1] + 1 - traced.axis) / r, -1, 1)))
    start = max(float(np.median(lefts)), -MAX_ANGLE)
    end = min(float(np.median(rights)), MAX_ANGLE)
    if end - start < np.radians(5):
        return None

    radii = np.array([traced.radius_at(y) for y in range(top, bottom)])
    width = max(8, round(float(np.median(radii)) * (end - start)))
    angles = start + (np.arange(width) + 0.5) / width * (end - start)
    ys = np.arange(top, bottom)[:, None] + 0.5 + np.zeros((1, width))
    xs = traced.axis + radii[:, None] * np.sin(angles)[None, :]

    rgb = _sample(np.asarray(seg.image, dtype=float), xs, ys)
    alpha = _sample(mask[..., None].astype(float), xs, ys)[..., 0]
    if flatten:
        rgb = _flatten(rgb, alpha)
    rgba = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)

    m = traced.meters_per_pixel
    return CutLabel(Image.fromarray(rgba, "RGBA"), from_=(traced.bottom - bottom) * m, to=(traced.bottom - top) * m,
                    arc=float(np.degrees(end - start)))
