"""Products as 3D model files: any shape, not only round ones (a model found
online, or one you have).

    normalize("raw.glb", "product.glb", height=0.15)    # upright, centred, standing on y = 0, 15 cm tall
    height, width = size("product.glb")
    key = install(studio, "product.glb")                # "products/model_<hash>.glb", for place_model

A product's model is kept in the Studio's units and pose: meters, Y up, its
front towards +Z, its base centre at the origin. Then it's placed like the
spun products: its base on the pedestal, at the origin.
"""

import hashlib
import shutil
from pathlib import Path

import numpy as np
import trimesh


def load(path: Path | str) -> trimesh.Scene:
    return trimesh.load(str(path), force="scene")


def size(path: Path | str) -> tuple[float, float]:
    """The model's height (Y) and widest horizontal size (X or Z), in meters."""
    lo, hi = load(path).bounds
    return float(hi[1] - lo[1]), float(max(hi[0] - lo[0], hi[2] - lo[2]))


def normalize(source: Path | str, out: Path | str, height: float, up: str = "+y", turn: float = 0.0) -> Path:
    """`source` as a product: rotated so `up` ("+y", "+z", "-z", ...) points up
    and turned `turn` degrees about the vertical, centred over the origin,
    standing on y = 0 and scaled to `height` meters; written as a GLB with
    vertex normals."""
    scene = load(source)
    axis = {"x": 0, "y": 1, "z": 2}[up[1]]
    sign = -1.0 if up[0] == "-" else 1.0
    if axis != 1 or sign < 0:
        direction = np.zeros(3)
        direction[axis] = sign
        scene.apply_transform(_rotation_between(direction, np.array([0.0, 1.0, 0.0])))
    if turn:
        scene.apply_transform(trimesh.transformations.rotation_matrix(np.radians(turn), [0, 1, 0]))
    lo, hi = scene.bounds
    scene.apply_translation([-(lo[0] + hi[0]) / 2, -lo[1], -(lo[2] + hi[2]) / 2])
    scene.apply_scale(height / max(hi[1] - lo[1], 1e-9))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(out), file_type="glb", include_normals=True)   # without them the Studio can't light it
    return out


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The 4x4 rotation taking unit vector `a` to `b`."""
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:   # parallel: none, or half a turn about any perpendicular axis
        return np.eye(4) if c > 0 else trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])
    return trimesh.transformations.rotation_matrix(np.arccos(np.clip(c, -1, 1)), v)


def install(studio, path: Path | str) -> str:
    """Copies the model into the Studio's assets (products/, next to the
    spun products) under a name from its content, so the same model is one
    file however often it's placed. Returns its asset key for place_model."""
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    key = f"products/model_{digest}{path.suffix.lower()}"
    target = Path(studio.exe).parent / "assets" / key
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return key
