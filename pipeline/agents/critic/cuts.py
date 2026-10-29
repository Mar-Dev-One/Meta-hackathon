"""The critic's measured checks across cuts: the last frame of each shot
against the first frame of the next. Good shots can still make a jarring cut.

    cuts = await measure_cuts(studio, sb, out_dir)     # the storyboard built in the Studio
    cuts[0].flags                                       # [Flag(severity, "continuity", time, problem)]

At each cut, from the Studio and the two frames (rendered three ways, as
measure.py does, for the product's exact pixels):

    view_jump      degrees the side of the product facing the camera turns: the camera's
                   angle around it, less the product's own turn (a spin track)
    set_light      the lights' total intensity after / before, from the Studio
    set_colour     Lab distance between the lights' mean colour before and after
    light_jump     the frame's mean lightness (L*, 0-100) after, less before
    colour_jump    Lab distance between the two frames' mean colour cast (a*, b*)
    product_light  the product's median lightness after, less before
    centre_jump    how far the product's centre moves on screen (share of the frame's height)
    size_ratio     its height in the frame after / before

Cutting on a change of angle and size is what a cut is for; the flags are for
jumps a viewer feels: the product swinging to its other side, the set's light
or its colour changing as if it were another set. The light is read from the
lights, not the pixels: a new framing changes what's bright in the frame (a
close-up full of lit label, a wide shot full of dark wall) as much as a light
does, so the frame's numbers are reported for the vision pass, not flagged.
"""

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from pipeline.agents.analyst.palette import to_lab
from pipeline.schemas import Storyboard
from pipeline.studio.build import PRODUCT
from pipeline.studio.render import frame_size

from .measure import Flag, Frame, _passes, measure_frame, product_mask

# Flag thresholds: (minor, major).
VIEW_JUMP = (90.0, 150.0)       # degrees (the director's craft rule: about 90 at most, unless it's meant to surprise)
SET_LIGHT = (1.35, 2.0)         # the lights' total intensity, after / before or before / after
SET_COLOUR = (10.0, 20.0)       # Lab distance of the lights' mean colour


@dataclass
class Cut:
    index: int                    # 0 for the cut from the first shot to the second
    before: str                   # shot ids
    after: str
    time: float                   # the first frame of `after`
    frames: list[str] = field(default_factory=list)   # the last frame before and the first after
    view: list[float] = field(default_factory=list)    # the side of the product facing the camera, degrees (0 its front)
    view_jump: float = 0.0
    set_light: float = 1.0
    set_colour: float = 0.0
    light_jump: float = 0.0
    colour_jump: float = 0.0
    product_light: float = 0.0
    centre_jump: float = 0.0
    size_ratio: float = 1.0
    flags: list[Flag] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def _wrap(degrees: float) -> float:
    """-180 .. 180."""
    return (degrees + 180.0) % 360.0 - 180.0


async def facing(studio, t: float) -> tuple[float, float]:
    """The side of the product facing the camera at `t`, as (degrees around
    it from its front, degrees above it)."""
    await studio.call("timeline.seek", t=t)
    camera = (await studio.call("camera.get"))["position"]
    transform = (await studio.call("entity.get", entity=PRODUCT))["components"]["Transform"]
    dx, dy, dz = (c - p for c, p in zip(camera, transform["position"]))
    around = math.degrees(math.atan2(dx, dz)) - transform["rotation_deg"][1]
    return _wrap(around), math.degrees(math.atan2(dy, math.hypot(dx, dz)))


def _srgb(linear: list[float]) -> np.ndarray:
    """A light's linear RGB colour, its brightest channel at 1, as sRGB 0..255."""
    c = np.clip(np.array(linear, float) / max(max(linear), 1e-6), 0, 1)
    return 255 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


async def lights_at(studio, t: float) -> tuple[float, np.ndarray]:
    """The lights at `t`: their total intensity, and their colour weighted by
    intensity, in Lab."""
    await studio.call("timeline.seek", t=t)
    total, colour = 0.0, np.zeros(3)
    for e in (await studio.call("scene.describe"))["entities"]:
        light = (await studio.call("entity.get", entity=e["name"]))["components"].get("Light")
        if light and light.get("intensity", 0) > 0:
            total += light["intensity"]
            colour += light["intensity"] * to_lab(_srgb(light["color"])[None])[0]
    return total, colour / max(total, 1e-6)


def _grade(value: float, limits: tuple[float, float]) -> str | None:
    minor, major = limits
    return "major" if value >= major else "minor" if value >= minor else None


def cut_flags(cut: Cut, revealing: bool) -> list[Flag]:
    """What's jarring about a cut. A reveal (fading in from dark) may change
    the light across it."""
    out, t = [], cut.time
    name = f"the cut from {cut.before} to {cut.after}"
    if s := _grade(abs(cut.view_jump), VIEW_JUMP):
        out.append(Flag(s, "continuity", t, f"{name} turns the product {abs(cut.view_jump):.0f} degrees (from "
                                            f"{cut.view[0]:.0f} to {cut.view[1]:.0f} around it, 0 its front)"))
    if not revealing:
        change = max(cut.set_light, 1 / max(cut.set_light, 1e-6))
        if s := _grade(change, SET_LIGHT):
            out.append(Flag(s, "continuity", t, f"{name} {'brightens' if cut.set_light > 1 else 'dims'} the lights "
                                                f"{change:.1f} times, as if it were another set"))
        if s := _grade(cut.set_colour, SET_COLOUR):
            out.append(Flag(s, "continuity", t, f"{name} changes the lights' colour (Lab distance "
                                                f"{cut.set_colour:.0f}), as if it were another set"))
    return out


async def measure_cuts(studio, sb: Storyboard, out_dir: Path, short: int = 540, samples: int = 4) -> list[Cut]:
    """Every cut of the storyboard (already built in the Studio) measured;
    its frames and masks in `out_dir`."""
    if len(sb.shots) < 2:
        return []
    out_dir = Path(out_dir)
    width, height = frame_size(sb.aspect, short)
    starts = sb.shot_starts()
    step = 1.0 / sb.fps
    cuts = [Cut(i, a.id, b.id, round(starts[i + 1], 3)) for i, (a, b) in enumerate(zip(sb.shots, sb.shots[1:]))]
    times = [t for c in cuts for t in (round(c.time - step, 3), c.time)]
    shown, paths, alone, empty = await _passes(studio, times, width, height, out_dir, samples)
    fade_in = sb.look.lighting.fade_in or 0.0

    for n, cut in enumerate(cuts):
        frames, means = [], []
        for k in (2 * n, 2 * n + 1):
            bounds = await studio.call("shot.bounds", entity=PRODUCT, t=times[k], width=width, height=height)
            frame = Frame(time=times[k], path=paths[k], bounds=bounds)
            measure_frame(frame, shown[k], product_mask(alone[k], empty[k], bounds.get("box")), [], {})
            frames.append(frame)
            means.append(to_lab(shown[k].reshape(-1, 3).astype(float)).mean(0))
        a, b = frames
        cut.frames = [a.path, b.path]
        cut.view = [round((await facing(studio, t))[0], 1) for t in (a.time, b.time)]
        cut.view_jump = round(_wrap(cut.view[1] - cut.view[0]), 1)
        (ia, ca), (ib, cb) = [await lights_at(studio, t) for t in (a.time, b.time)]
        cut.set_light = round(ib / max(ia, 1e-6), 2)
        cut.set_colour = round(float(np.linalg.norm(cb - ca)), 1)
        cut.light_jump = round(float(means[1][0] - means[0][0]), 1)
        cut.colour_jump = round(float(np.linalg.norm(means[1][1:] - means[0][1:])), 1)
        if a.fill_area and b.fill_area:
            cut.product_light = round(b.product_l - a.product_l, 1)
            # In shares of the frame's height, both ways (x is a share of the width).
            cut.centre_jump = round(math.hypot((b.center[0] - a.center[0]) * width / height,
                                               b.center[1] - a.center[1]), 3)
            cut.size_ratio = round(b.fill_height / a.fill_height, 2)
        cut.flags = cut_flags(cut, revealing=cut.time < fade_in)
    return cuts
