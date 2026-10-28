"""The product's colours from its pixels: k-means in Lab (where distance is
how different colours look), part by part.

    swatches = palette(seg)       # [Swatch(hex, role, share)], the BrandProfile's palette
    strip(swatches).save("palette.png")

Roles: the body's (the product without cap and label) biggest colour is
"product", the cap's is "accent"; the label's biggest is "label" and the one
that stands out most from it is "text". Light and shade on one material
make clusters of one hue at different lightness and saturation, so a part
keeps one colour per family: the greys, or a hue (amber perfume in clear
glass is two). A colour already in the palette from another part isn't
repeated. Shares are of the whole product's pixels.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pipeline.schemas.brand import Swatch

from .segment import Segmentation

SAMPLES = 20000       # pixels clustered per region (spread evenly)
SAME = 10.0           # Lab distance under which two clusters are one
REPEAT = 4.0          # Lab distance under which a colour is already in the palette
GREY = 8.0            # chroma under which a colour is a grey (its hue means nothing)
HUE = 30.0            # degrees of hue between two colour families
TEXT = 25.0           # Lab distance the label's text needs from its paper
MIN_SHARE = 0.03      # of its region: smaller clusters are noise or shading
MIN_TEXT = 0.005      # of the label: thin lettering is only a little of it


def to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB 0..255 (N x 3) to CIE Lab (D65)."""
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.column_stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])])


def kmeans(points: np.ndarray, k: int, iterations: int = 25, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Cluster centres and each point's cluster; k-means++ start, fixed seed."""
    rng = np.random.default_rng(seed)
    centres = [points[rng.integers(len(points))]]
    for _ in range(1, k):
        d = np.min([((points - c) ** 2).sum(1) for c in centres], axis=0)
        centres.append(points[rng.choice(len(points), p=d / d.sum())] if d.sum() > 0 else points[0])
    centres = np.array(centres)
    for _ in range(iterations):
        labels = ((points[:, None] - centres[None]) ** 2).sum(2).argmin(1)
        moved = np.array([points[labels == i].mean(0) if (labels == i).any() else centres[i] for i in range(k)])
        if np.allclose(moved, centres):
            break
        centres = moved
    return centres, labels


def _clusters(rgb: np.ndarray, k: int, min_share: float = MIN_SHARE) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """(Lab centre, mean sRGB, share of these pixels), biggest first; near
    duplicates merged, tiny ones dropped."""
    if len(rgb) > SAMPLES:
        rgb = rgb[np.linspace(0, len(rgb) - 1, SAMPLES).astype(int)]
    lab = to_lab(rgb.astype(float))
    centres, labels = kmeans(lab, min(k, len(lab)))
    groups = [labels == i for i in range(len(centres))]
    merged: list[np.ndarray] = []
    for g in sorted(groups, key=lambda g: -g.sum()):
        if not g.any():
            continue
        home = next((i for i, m in enumerate(merged) if np.linalg.norm(lab[m].mean(0) - lab[g].mean(0)) < SAME), None)
        if home is None:
            merged.append(g)
        else:
            merged[home] = merged[home] | g
    out = [(lab[g].mean(0), rgb[g].mean(0), g.sum() / len(rgb)) for g in merged]
    return sorted((c for c in out if c[2] >= min_share), key=lambda c: -c[2])


def _hex(rgb: np.ndarray) -> str:
    r, g, b = np.clip(rgb.round(), 0, 255).astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def _family(lab: np.ndarray) -> float | None:
    """A colour's hue in degrees, or None for a grey."""
    if np.hypot(lab[1], lab[2]) < GREY:
        return None
    return float(np.degrees(np.arctan2(lab[2], lab[1])) % 360)


def _same_family(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return min(abs(a - b), 360 - abs(a - b)) < HUE


def _hues(rgb: np.ndarray, k: int) -> list[tuple[np.ndarray, np.ndarray, float]]:
    """A part's colour families (one hue, or the greys, in all its light and
    shade), each as its clusters' mean weighted by share: a brushed metal's
    highlights and shadows average to its silver. Biggest first."""
    families: list[list] = []
    for c in _clusters(rgb, k):
        home = next((f for f in families if _same_family(_family(c[0]), _family(f[0][0]))), None)
        if home is None:
            families.append([c])
        else:
            home.append(c)
    out = []
    for f in families:
        shares = np.array([c[2] for c in f])
        out.append((np.average([c[0] for c in f], axis=0, weights=shares),
                    np.average([c[1] for c in f], axis=0, weights=shares), float(shares.sum())))
    return sorted(out, key=lambda c: -c[2])


def palette(seg: Segmentation, k: int = 5) -> list[Swatch]:
    image = np.asarray(seg.image)
    product = np.asarray(seg.product.mask) > 127
    nothing = np.zeros_like(product)
    label = np.asarray(seg.parts["label"].mask) > 127 if "label" in seg.parts else nothing
    cap = np.asarray(seg.parts["cap"].mask) > 127 if "cap" in seg.parts else nothing
    total = product.sum()
    swatches: list[Swatch] = []
    seen: list[np.ndarray] = []

    def add(found, region: np.ndarray, roles: list[str]) -> None:
        for (lab, rgb, share), role in zip(found, roles):
            if any(np.linalg.norm(lab - other) < REPEAT for other in seen):
                continue   # already in the palette (a cap the colour of the body)
            seen.append(lab)
            swatches.append(Swatch(hex=_hex(rgb), role=role, share=round(share * region.sum() / total, 3)))

    body = product & ~label & ~cap
    if body.any():
        found = _hues(image[body], k)
        add(found, body, ["product"] + ["accent"] * (len(found) - 1))
    if cap.any():
        found = _hues(image[cap & ~label], k)
        add(found, cap, ["accent"] * len(found))
    if label.any():
        found = _clusters(image[label], 4, MIN_TEXT)
        paper = found[0]
        text = max(found[1:], key=lambda c: np.linalg.norm(c[0] - paper[0]), default=None)
        add([paper], label, ["label"])
        if text is not None and np.linalg.norm(text[0] - paper[0]) >= TEXT:
            add([text], label, ["text"])
    return swatches[:8]


def strip(swatches: list[Swatch], width: int = 900, height: int = 120) -> Image.Image:
    """The swatches side by side, as wide as their shares (at least a little),
    each with its hex and role."""
    out = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=15)
    weights = [max(s.share, 0.06) for s in swatches]
    x = 0.0
    for s, w in zip(swatches, weights):
        x1 = x + width * w / sum(weights)
        rgb = tuple(int(s.hex[i:i + 2], 16) for i in (1, 3, 5))
        draw.rectangle([x, 0, x1, height], fill=rgb)
        ink = (0, 0, 0) if sum(rgb) > 380 else (255, 255, 255)
        draw.text((x + 6, height - 42), f"{s.hex}\n{s.role} {s.share:.0%}", fill=ink, font=font)
        x = x1
    return out
