"""The label cut from the photo and unrolled, to wrap round the 3D body.

    cut = unroll(seg, traced)
    cut.image.save("label.png")       # RGBA, flat: as printed, before it went round the bottle
    {"image": "label.png", "part": "body", "from": cut.from_, "to": cut.to, "arc": cut.arc}   # product.create's label

On a round body a point at angle a from the front shows at x = axis + r sin a,
so the photo squeezes a label towards the sides. Unrolling samples the photo
at those x for evenly spaced angles, row by row with that row's radius: the
inverse of the Studio's wrap. Past MAX_ANGLE the side is too foreshortened
to read, so a label that runs round the back is cut there; one that
reaches both sides of the silhouette goes all the way round, so the cut is
centred on a full turn and its edges' colours, row by row, carry on round
the back (a printed band, a paper wrap). The light on the
photo (darker towards the sides) is divided out using the label's paper,
its brightest pixels down each column, so the Studio's lights don't add
theirs to it.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageChops, ImageFilter
from scipy.ndimage import binary_erosion, gaussian_filter, label as label_pieces

from .palette import to_lab
from .profile import Traced, _median
from .segment import Region, Segmentation

MAX_ANGLE = np.radians(72)
MAX_GAIN = 1.8      # the most a column is brightened to undo the shading
INSET = 0.0005      # meters a label kept to its part stays inside the part's ends
ON_PART = 0.5       # of the label's height: the least that must lie on a part's side to wrap it there
PRINT = 30.0        # Lab distance (lightness counting half) from the body's colour that's print, not its shade
FINE = 12.0         # the same from its neighbourhood (FINE_REACH of its height around): fine line art, gold leaf
FINE_REACH = 0.01
INSIDE = 0.005      # of its height: how far in from the body's edges print is looked for (not a cap's seam)
BLOB = 0.0004       # of the body's pixels: a piece of print smaller than this is a speck (fabric, noise)
PRINT_SHARE = (0.005, 0.7)   # of the body: less is specks, more is no body colour to tell print from


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


def _round_the_back(rgba: np.ndarray, arc: float) -> np.ndarray:
    """The cut (covering `arc` degrees) centred on a full turn, the rest of
    each row its edges' median colour."""
    edge = max(2, rgba.shape[1] // 30)
    fill = np.median(np.concatenate([rgba[:, :edge], rgba[:, -edge:]], axis=1), axis=1)
    width = round(rgba.shape[1] * 360 / arc)
    out = np.repeat(fill[:, None, :], width, axis=1)
    left = (width - rgba.shape[1]) // 2
    out[:, left:left + rgba.shape[1]] = rgba
    return out


def unroll(seg: Segmentation, traced: Traced, flatten: bool = True, whole: bool = False) -> CutLabel | None:
    """The label as printed (None if the photo has no label). Its sides are
    where most of its rows end (a paper label's, past its spill), or with
    `whole` its widest (print: a logo's letters, few rows reaching across)."""
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
    left, right = (min(lefts), max(rights)) if whole else (np.median(lefts), np.median(rights))
    wraps = left <= -MAX_ANGLE and right >= MAX_ANGLE
    start = max(float(left), -MAX_ANGLE)
    end = min(float(right), MAX_ANGLE)
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
    rgba = np.dstack([rgb, alpha * 255])
    arc = float(np.degrees(end - start))
    if wraps:
        rgba, arc = _round_the_back(rgba, arc), 360.0
    rgba = rgba.round().astype(np.uint8)

    m = traced.meters_per_pixel
    return CutLabel(Image.fromarray(rgba, "RGBA"), from_=(traced.bottom - bottom) * m, to=(traced.bottom - top) * m,
                    arc=arc)


def printed(seg: Segmentation) -> Region | None:
    """The print on the body itself, as a label region, for a product with
    no paper label (a can's logo, a tube's lettering, SAM finds no "label"):
    the body's pixels far from its own colour (big letters), or from their
    neighbourhood's (fine line art), lightness counting half so a can's
    darker edges and highlight stripes, which change slowly, stay body.
    Wrapped, only the print shows (the region is the label's alpha) over
    the body's material. None when there's too little to be print, or too
    much to tell it from the body."""
    product = np.asarray(seg.product.mask) > 127
    cap = np.asarray(seg.parts["cap"].mask) > 127 if "cap" in seg.parts else np.zeros_like(product)
    body = product & ~cap
    if body.sum() < 100:
        return None
    weight = np.array([0.5, 1.0, 1.0])
    lab = to_lab(np.asarray(seg.image, dtype=float).reshape(-1, 3)).reshape(*body.shape, 3)
    far = np.linalg.norm((lab - np.median(lab[body], axis=0)) * weight, axis=2) > PRINT
    reach = FINE_REACH * (seg.product.box[3] - seg.product.box[1])   # around, within the body only
    near = gaussian_filter(body.astype(float), reach)
    around = np.dstack([gaussian_filter(lab[..., k] * body, reach) for k in range(3)]) / np.maximum(near, 1e-6)[..., None]
    fine = np.linalg.norm((lab - around) * weight, axis=2) > FINE
    inside = binary_erosion(body, iterations=max(2, round(INSIDE * (seg.product.box[3] - seg.product.box[1]))))
    big = Image.fromarray((far & inside).astype(np.uint8) * 255, "L").filter(ImageFilter.MinFilter(3))
    thin = Image.fromarray((fine & inside).astype(np.uint8) * 255, "L").filter(ImageFilter.MedianFilter(3))
    found = np.asarray(ImageChops.lighter(big, thin)) > 127
    pieces, count = label_pieces(found)
    sizes = np.bincount(pieces.ravel(), minlength=count + 1)
    keep = sizes >= BLOB * body.sum()
    keep[0] = False
    image = Image.fromarray(keep[pieces].astype(np.uint8) * 255, "L").filter(ImageFilter.MaxFilter(3))   # whole edges
    image = Image.fromarray(np.where(body, np.asarray(image), 0).astype(np.uint8), "L")
    share = (np.asarray(image) > 127).sum() / body.sum()
    if not PRINT_SHARE[0] <= share <= PRINT_SHARE[1]:
        return None
    return Region("label", "print on the body", image, image.getbbox())


def onto(cut: CutLabel, parts) -> CutLabel | None:
    """The label on the part its band lies on most (segmentation can call
    most of a tube its cap), kept to that part's side: a band reaching past
    it, into a lid, would wrap thin air. None if no part holds ON_PART of it.
    The image keeps its rows: a sliver past the part's end is squeezed in."""
    def side(part) -> tuple[float, float]:   # the heights where the part has a radius
        ys = [y for r, y in part.profile if r > 0]
        return (min(ys), max(ys)) if ys else (0.0, 0.0)

    def overlap(part) -> float:
        lo, hi = side(part)
        return max(0.0, min(cut.to, hi) - max(cut.from_, lo))

    best = max(parts, key=overlap, default=None)
    if best is None or overlap(best) < ON_PART * (cut.to - cut.from_):
        return None
    lo, hi = side(best)
    from_ = cut.from_ if cut.from_ > lo else lo + INSET
    to = cut.to if cut.to < hi else hi - INSET
    return CutLabel(cut.image, from_=from_, to=to, arc=cut.arc, part=best.name)
