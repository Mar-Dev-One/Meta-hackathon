"""The set library: real surfaces for the pedestal and backdrop, and light
environments (HDRIs) that light the product, show in its reflections and
can stand behind it as a blurred background. All from Poly Haven
(polyhaven.com), CC0: free for any use, no credit needed. Each is fetched
the first time it's used and kept in cache/sets/.

    texture = surface_texture("cream_marble")    # a .jpg to give backdrop.create's `texture`
    key = install_hdri(studio, "golden_hour")    # "hdri/<id>_2k.hdr", for environment.set's `hdri`

The names are what the director chooses from (the Storyboard schema lists
them); the ids are Poly Haven's.
"""

import shutil
from functools import cache
from pathlib import Path

from .common import fetch

FILES = "https://dl.polyhaven.org/file/ph-assets"
CACHE = Path("cache/sets")

# name: (Poly Haven id, roughness, meters per repeat, what it is)
SURFACES = {
    "cream_marble": ("marble_01", 0.2, 0.6, "warm cream marble with soft veins, polished: luxury, timeless"),
    "granite": ("granite_tile", 0.35, 0.5, "dark grey speckled granite: luxury, masculine, tech"),
    "terrazzo": ("terrazzo_tiles", 0.4, 0.6, "terrazzo, flecks in warm stone: modern, playful, design"),
    "dark_wood": ("dark_wood", 0.5, 0.8, "dark reddish-brown wood: warm, crafted, premium"),
    "light_wood": ("smoked_walnut_veneer", 0.55, 0.8, "light warm wood veneer: natural, Scandinavian, calm"),
    "concrete": ("brushed_concrete", 0.8, 1.0, "smooth grey-brown concrete: urban, minimal, raw"),
    "stone": ("rock_face_03", 0.9, 0.8, "rough brown natural rock: outdoors, rugged, organic"),
    "sand": ("sand_01", 0.95, 0.6, "fine pale beach sand: summer, sun care, coastal"),
    "plaster": ("beige_wall_001", 0.9, 1.5, "warm beige plaster: soft, natural, skincare (a wall)"),
    "blue_linen": ("rough_linen", 0.9, 0.4, "soft blue linen cloth: fresh, calm, home"),
    "red_velvet": ("velour_velvet", 0.8, 0.4, "deep red velvet: luxury, evening, romance"),
}

# name: (Poly Haven id, what it is)
LIGHTS = {
    "studio": ("studio_small_09", "a small photo studio: soft, neutral light (the default)"),
    "studio_bright": ("photo_studio_01", "a large bright photo studio: clean, even, high key"),
    "studio_warm": ("brown_photostudio_02", "a studio with warm brown walls: cosy, crafted"),
    "fireplace": ("fireplace", "a room lit by a fire: warm, intimate, evening"),
    "golden_hour": ("spruit_sunrise", "open land at sunrise: golden, natural, hopeful"),
    "sunset_sky": ("the_sky_is_on_fire", "a blazing orange sunset sky: dramatic, bold"),
    "daylight": ("kloofendal_48d_partly_cloudy_puresky", "a clear blue sky with soft clouds: fresh, outdoors"),
    "city_night": ("shanghai_bund", "a city's lights at night: urban, energetic, nightlife"),
}


def surface_texture(name: str) -> Path:
    """The surface's colour image (2k jpg), fetched once."""
    pid = SURFACES[name][0]
    path = CACHE / "textures" / f"{pid}_diff_2k.jpg"
    if not path.exists():
        fetch(f"{FILES}/Textures/jpg/2k/{pid}/{pid}_diff_2k.jpg", path)
    return path


@cache
def surface_colour(name: str) -> str:
    """The surface's average colour, "#RRGGBB" (what it reads as from afar)."""
    from PIL import Image

    image = Image.open(surface_texture(name)).convert("RGB").resize((1, 1), Image.Resampling.BOX)
    return "#{:02X}{:02X}{:02X}".format(*image.getpixel((0, 0)))


def hdri_file(name: str) -> Path:
    """The light environment's HDRI (2k .hdr), fetched once."""
    pid = LIGHTS[name][0]
    path = CACHE / "hdri" / f"{pid}_2k.hdr"
    if not path.exists():
        fetch(f"{FILES}/HDRIs/hdr/2k/{pid}_2k.hdr", path)
    return path


def install_hdri(studio, name: str) -> str:
    """The light environment copied into the Studio's assets (the HDRI must
    be there); its key for environment.set."""
    source = hdri_file(name)
    key = f"hdri/{source.name}"
    target = Path(studio.exe).parent / "assets" / key
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return key
