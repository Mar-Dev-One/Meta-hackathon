"""A downloaded model in the product's own colours, its texture's detail
kept: palette transfer. The model's colours are measured where its surfaces
sample its textures (each face's colour, weighted by its area, so a
texture's unused corners don't count), clustered into as many groups as
the photo has main colours, and matched to them either by size (the
model's biggest colour region takes the photo's biggest colour, and so on)
or by lightness (its darkest region takes the darkest colour): neither is
right for every model (a sneaker's grey upper is its biggest region and
should go white; a watch's black dial is its smallest and should stay
dark), so versions() makes both, for someone to choose by looking. Every texel then
moves to its group's new colour, keeping its light and shade relative to
the group (seams, knit, grooves survive); texels between groups blend.

    recolour("product.glb", [("#222221", 0.7), ("#BCD250", 0.2)])   # VOLT: black, lime accents
    versions("product.glb", colours, folder)    # {"size": ..., "lightness": ...}, the distinct ones
"""

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from pipeline.agents.analyst.palette import kmeans, to_lab

SAMPLES = 20000          # face colours drawn (by area) to cluster
SOFT = 12.0              # Lab distance over which a texel blends between groups
DETAIL = (1.0, 0.35, 0.35)   # how much of a texel's own difference from its group it keeps: L, a, b
BY = ("size", "lightness")   # ways of pairing the model's colour regions with the photo's colours


def to_rgb(lab: np.ndarray) -> np.ndarray:
    """CIE Lab (D65, N x 3) to sRGB 0..255."""
    fy = (lab[:, 0] + 16) / 116
    f = np.column_stack([fy + lab[:, 1] / 500, fy, fy - lab[:, 2] / 200])
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    rgb = xyz @ np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]]).T
    rgb = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.clip(rgb, 0, None) ** (1 / 2.4) - 0.055)
    return np.clip(rgb * 255, 0, 255)


def _hex_rgb(hex_colour: str) -> np.ndarray:
    return np.array([int(hex_colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], float)


def _material(mesh):
    return getattr(mesh.visual, "material", None)


def _factor(material) -> np.ndarray:
    """The material's colour factor, RGBA 0..255, its colour linear (as glTF keeps it)."""
    f = getattr(material, "baseColorFactor", None)
    f = np.array(f if f is not None else [255, 255, 255, 255], float)
    return f * 255 if f.max() <= 1.0 else f


def _to_linear(srgb: np.ndarray) -> np.ndarray:
    """sRGB 0..255 to linear 0..1."""
    c = np.asarray(srgb, float) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _to_srgb(linear: np.ndarray) -> np.ndarray:
    """Linear 0..1 to sRGB 0..255."""
    c = np.clip(linear, 0, 1)
    return 255 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def _seen(texels: np.ndarray, factor: np.ndarray) -> np.ndarray:
    """Texture colours (sRGB 0..255) as shown, times a linear factor (0..255)."""
    return _to_srgb(_to_linear(texels) * factor[:3] / 255)


def _texture(material) -> Image.Image | None:
    return getattr(material, "baseColorTexture", None) if material is not None else None


def _samples(scene: trimesh.Scene) -> tuple[np.ndarray, np.ndarray]:
    """Every face's colour as seen (texture at its UV centre, times the
    material's factor) and its area."""
    colours, weights = [], []
    for mesh in scene.geometry.values():
        material = _material(mesh)
        factor = _factor(material)
        texture = _texture(material)
        uv = getattr(mesh.visual, "uv", None)
        if texture is not None and uv is not None and len(uv) == len(mesh.vertices):
            pixels = np.asarray(texture.convert("RGB"), float)
            h, w = pixels.shape[:2]
            centres = uv[mesh.faces].mean(1) % 1.0
            x = np.clip((centres[:, 0] * (w - 1)).astype(int), 0, w - 1)
            y = np.clip(((1 - centres[:, 1]) * (h - 1)).astype(int), 0, h - 1)
            colours.append(_seen(pixels[y, x], factor))
        else:
            colours.append(np.tile(_to_srgb(factor[:3] / 255), (len(mesh.faces), 1)))
        weights.append(mesh.area_faces)
    return np.concatenate(colours), np.concatenate(weights)


def _move(lab: np.ndarray, centres: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """Each colour moved from its group's centre to the group's target,
    keeping its own difference from the centre (DETAIL), blended between
    groups it's near."""
    d2 = ((lab[:, None, :] - centres[None]) ** 2).sum(2)
    w = np.exp(-(d2 - d2.min(1, keepdims=True)) / (2 * SOFT ** 2))
    w /= w.sum(1, keepdims=True)
    moved = targets[None] + (lab[:, None, :] - centres[None]) * np.array(DETAIL)
    out = (w[..., None] * moved).sum(1)
    out[:, 0] = np.clip(out[:, 0], 0, 100)
    return out


def _pairing(path: Path, colours: list[tuple[str, float]], by: str, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The model's colour groups' centres and, for each, the photo's colour
    it becomes (Lab), paired `by` size or lightness."""
    targets = sorted(colours, key=lambda c: -c[1])[:4]   # the photo's colours, biggest first
    rgb, area = _samples(trimesh.load(str(path), force="scene"))
    k = min(len(targets), len(rgb))
    draw = np.random.default_rng(seed).choice(len(rgb), size=SAMPLES, p=area / area.sum())
    centres, labels = kmeans(to_lab(rgb[draw]), k, seed=seed)
    goal = to_lab(np.array([_hex_rgb(h) for h, _ in targets[:k]]))
    if by == "size":
        mine, theirs = np.argsort(-np.bincount(labels, minlength=k)), np.arange(k)
    else:
        mine, theirs = np.argsort(centres[:, 0]), np.argsort(goal[:, 0])
    return centres[mine], goal[theirs]


def recolour(path: Path | str, colours: list[tuple[str, float]], out: Path | str | None = None,
             by: str = "size", seed: int = 0) -> Path:
    """The model at `path` in `colours` ((hex, share), the photo's main
    colours, up to 4), its regions paired with them `by` size or lightness;
    saved to `out` (default: in place)."""
    path = Path(path)
    out = Path(out or path)
    if not colours:
        return path
    centres, goal = _pairing(path, colours, by, seed)
    scene = trimesh.load(str(path), force="scene")

    done: dict[int, Image.Image] = {}
    for mesh in scene.geometry.values():
        material = _material(mesh)
        if material is None:
            continue
        factor = _factor(material)
        texture = _texture(material)
        if texture is not None:
            if id(texture) not in done:
                pixels = np.asarray(texture.convert("RGBA"), float)
                seen = _seen(pixels[..., :3], factor)
                moved = to_rgb(_move(to_lab(seen.reshape(-1, 3)), centres, goal)).reshape(seen.shape)
                done[id(texture)] = Image.fromarray(np.dstack([moved, pixels[..., 3]]).astype(np.uint8), "RGBA")
            material.baseColorTexture = done[id(texture)]
            material.baseColorFactor = [255, 255, 255, int(factor[3])]   # the colour is in the texture now
        else:
            moved = to_rgb(_move(to_lab(_to_srgb(factor[None, :3] / 255)), centres, goal))[0]
            material.baseColorFactor = [int(round(v)) for v in 255 * _to_linear(moved)] + [int(factor[3])]
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb", include_normals=True)
    return out


def versions(path: Path | str, colours: list[tuple[str, float]], folder: Path | str,
             seed: int = 0) -> dict[str, Path]:
    """The model recoloured each of BY ways, one file each in `folder`;
    a way pairing the colours just as an earlier one does is left out."""
    path, folder = Path(path), Path(folder)
    out, seen = {}, []
    for by in BY:
        centres, goal = _pairing(path, colours, by, seed)
        pairs = sorted(zip(map(tuple, np.round(centres, 3)), map(tuple, np.round(goal, 3))))
        if pairs in seen:
            continue
        seen.append(pairs)
        out[by] = recolour(path, colours, folder / f"{path.stem}_{by}.glb", by=by, seed=seed)
    return out
