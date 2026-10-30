"""Painted backgrounds: a picture (Muse Image's, from the director's prompt)
made into a light environment the Studio can show behind the product and
light it with, like the set library's HDRIs.

    key = install_painting(studio, prompt)   # "hdri/painted_<hash>.hdr", for environment.set's `hdri`

The picture covers the view in front of the camera (SPAN degrees across,
centred on azimuth 0); the rest of the sphere is the picture stretched and
blurred, so an orbit that looks past its edges sees its colours, not a
seam. Written as a Radiance .hdr (flat RGBE scanlines), which the Studio
reads; a picture's colours are its light, so it lights the product as
softly as it looks.
"""

import hashlib
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

WIDTH, HEIGHT = 4096, 2048   # the equirectangular map: 360 x 180 degrees
SPAN = 100.0                 # degrees across that the picture covers, in front
FRONT = 0.25                 # where azimuth 0 is across the map (0..1): the Studio looks there from the front
FEATHER = 0.08               # of the picture's size: its edges fade into the blur


def equirect(picture: Image.Image) -> np.ndarray:
    """The picture as an equirectangular map (float RGB, 0..1)."""
    picture = picture.convert("RGB")
    base = picture.resize((WIDTH // 8, HEIGHT // 8)).filter(ImageFilter.GaussianBlur(12)).resize((WIDTH, HEIGHT))
    width = round(WIDTH * SPAN / 360)
    height = min(round(width * picture.height / picture.width), HEIGHT)
    front = picture.resize((width, height), Image.Resampling.LANCZOS)
    # A mask that's 1 in the middle and fades to 0 at the picture's edges.
    fy = np.minimum(np.linspace(0, 1, height), np.linspace(1, 0, height)) / FEATHER
    fx = np.minimum(np.linspace(0, 1, width), np.linspace(1, 0, width)) / FEATHER
    mask = np.clip(np.minimum.outer(fy, fx), 0, 1)[..., None]
    out = np.asarray(base, np.float32) / 255
    x0, y0 = round(WIDTH * FRONT - width / 2), round(HEIGHT / 2 - height / 2)
    region = out[y0:y0 + height, x0:x0 + width]
    out[y0:y0 + height, x0:x0 + width] = region * (1 - mask) + np.asarray(front, np.float32) / 255 * mask
    return out ** 2.2   # sRGB to linear light, as an HDR holds it


def write_hdr(rgb: np.ndarray, path: Path) -> Path:
    """Linear float RGB as a Radiance .hdr: RGBE, flat (uncompressed) scanlines."""
    peak = rgb.max(axis=2)
    mantissa, exponent = np.frexp(np.maximum(peak, 1e-32))
    scale = np.where(peak > 1e-32, mantissa * 256.0 / np.maximum(peak, 1e-32), 0)
    rgbe = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    rgbe[..., :3] = np.clip(rgb * scale[..., None], 0, 255).astype(np.uint8)
    rgbe[..., 3] = np.where(peak > 1e-32, exponent + 128, 0).astype(np.uint8)
    header = f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {rgb.shape[0]} +X {rgb.shape[1]}\n".encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + rgbe.tobytes())
    return path


def install_picture(studio, picture: Path | str, cache: Path = Path("cache/painted")) -> str:
    """A picture made into a light environment (cached by its content),
    copied into the Studio's assets; its key for environment.set."""
    picture = Path(picture)
    digest = hashlib.sha256(picture.read_bytes()).hexdigest()[:12]
    hdr = cache / f"painted_{digest}.hdr"
    if not hdr.exists():
        write_hdr(equirect(Image.open(picture)), hdr)
    key = f"hdri/{hdr.name}"
    target = Path(studio.exe).parent / "assets" / key
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(hdr, target)
    return key
