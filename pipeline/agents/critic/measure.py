"""The critic's measured checks: numbers from the renderer and the frames,
before any model looks. They ground the vision critic's judgment, and some
are verdicts on their own (a cut product is cut).

    shots = await measure(studio, sb, out_dir)     # the storyboard built in the Studio
    shots[0].flags                                 # [Flag(severity, category, time, problem)]
    shots[0].summary()                             # Critique.measured: {"fill_min": 0.31, ...}

Each shot is looked at three times (its start, middle and end), each frame
rendered three ways: as it is, with the product's shadow off, and without
the product (SSAO and bloom off for those two). The difference between the
last two is the product's exact pixels: a lathe product is filled row by
row, so glass that shows the set through it still counts. From the mask
and the frame:

    fill, cut          the product's share of the frame's height and area; which edges cut it
    centre, headroom   its centroid (0..1 from the top-left), the space above it
    separation         along its outline, the Lab distance between just inside and just
                       outside: `edge_lost` is the share of the outline that merges with
                       the background (a missing rim light)
    clipping           shares of its pixels blown to white and crushed to black
    palette            distance from each of the storyboard's colours to the nearest colour
                       rendered on the product: Lab, lightness at a third (the lighting
                       moves it), so it's mostly hue and saturation
    titles             the share of each visible title's box over the product

`shot.bounds` (the product's bounding box through the camera) is kept too,
as `bounds`. It errs towards "cut"; the mask decides.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pipeline.agents.analyst.palette import _clusters, to_lab
from pipeline.schemas import Storyboard
from pipeline.studio.build import PRODUCT
from pipeline.studio.render import frame_size

MOMENTS = (0.1, 0.5, 0.9)   # where in each shot it looks, as shares of the shot
REVEALING = 0.6             # of a reveal shot: until then the product may be out of frame or cut
CROP = 0.97                 # a shot asking for more fill than this crops the product on purpose (camera.move)
SIDE_CROP = 0.7             # ... and over this, a wide one's sides (camera.move's FRAMING_CLOSE)
CROPPED = 0.85              # ... where the product fills at least this much of the frame's height or width
CHANGED = 2                 # 0..255: a pixel the product changes by more than this is the product's
EDGE_STEP = 1 / 180         # of the frame's height: how far inside and outside the outline it compares
LOST = 10.0                 # Lab distance under which an outline point merges with the background
BLOWN, CRUSHED = 250, 3.0   # a channel at or over BLOWN is clipped; L* under CRUSHED is crushed
HUE_WEIGHTS = np.array([1 / 3, 1, 1])   # palette distance: L*, a*, b*

# Flag thresholds: (minor, major).
EDGE_LOST = (0.35, 0.6)
CLIPPED = (0.04, 0.12)
SMALL = (0.3, 0.18)          # share of the frame's height (an end card can be smaller: minor at most)
OVERLAP = (0.02, 0.1)        # of a title's box
PALETTE = (30.0, 45.0)


@dataclass
class Flag:
    severity: str        # "minor" or "major"
    category: str        # a Critique category
    time: float
    problem: str


@dataclass
class Frame:
    time: float
    path: str
    fill_height: float = 0.0          # the product's height as a share of the frame's
    fill_width: float = 0.0           # its width as a share of the frame's (a narrow frame crops by width)
    fill_area: float = 0.0            # its pixels' share of the frame
    cut_by: list[str] = field(default_factory=list)
    center: list[float] = field(default_factory=list)
    headroom: float = 0.0             # from the frame's top to the product's, share of the height
    edge_contrast: float = 0.0        # median Lab distance across the outline
    edge_lost: float = 0.0            # share of the outline under LOST
    product_l: float = 0.0            # median L* of the product
    background_l: float = 0.0         # median L* just around it
    clipped: float = 0.0              # share of the product's pixels blown
    crushed: float = 0.0              # share crushed
    palette: dict[str, float] = field(default_factory=dict)       # storyboard colour -> distance to the render
    title_overlap: dict[str, float] = field(default_factory=dict)  # title text -> share of its box over the product
    bounds: dict = field(default_factory=dict)


@dataclass
class ShotMeasure:
    shot: str
    frames: list[Frame]
    flags: list[Flag]

    def summary(self) -> dict[str, float]:
        """The numbers a Critique carries (`measured`): the worst of each
        over the shot's frames where the product can be seen."""
        f = [x for x in self.frames if x.fill_area] or self.frames
        out = {
            "unseen_frames": len(self.frames) - sum(bool(x.fill_area) for x in self.frames),
            "fill_min": min(x.fill_height for x in f), "fill_max": max(x.fill_height for x in f),
            "cut_frames": sum(bool(x.cut_by) for x in f),
            "headroom_min": min(x.headroom for x in f),
            "edge_contrast_min": min(x.edge_contrast for x in f), "edge_lost_max": max(x.edge_lost for x in f),
            "separation_min": min(abs(x.product_l - x.background_l) for x in f),
            "clipped_max": max(x.clipped for x in f), "crushed_max": max(x.crushed for x in f),
            "palette_distance_max": max((max(x.palette.values(), default=0.0) for x in f)),
            "title_overlap_max": max((max(x.title_overlap.values(), default=0.0) for x in f)),
        }
        return {k: round(float(v), 3) for k, v in out.items()}

    def to_json(self) -> dict:
        return {"shot": self.shot, "summary": self.summary(), "flags": [asdict(x) for x in self.flags],
                "frames": [asdict(x) for x in self.frames]}


def shot_times(sb: Storyboard) -> list[tuple[str, float]]:
    """(shot id, time) for every moment looked at."""
    return [(shot.id, round(start + m * shot.duration, 3))
            for start, shot in zip(sb.shot_starts(), sb.shots) for m in MOMENTS]


def storyboard_colours(sb: Storyboard) -> list[str]:
    """The product's colours as written: each part's, or for glass, the
    colour of what it holds (what a camera sees). Labels aren't included."""
    parts = list(sb.product.parts.values()) + list(sb.product.profile_parts or [])
    out = []
    for p in parts:
        colour = p.attenuation_color if p.transmission and p.attenuation_color else p.color
        if colour and colour.upper() not in out:
            out.append(colour.upper())
    return out


# --- Rendering ----------------------------------------------------------------------------


async def _render(studio, times: list[float], width: int, height: int, folder: Path, samples: int) -> list[np.ndarray]:
    result = await studio.call("shot.preview", times=times, width=width, height=height, samples=samples,
                               out_dir=str(folder))
    return [np.asarray(Image.open(f["path"]).convert("RGB")) for f in result["frames"]], \
           [f["path"] for f in result["frames"]]


async def _passes(studio, times, width, height, out_dir: Path, samples: int):
    """The frames as they are, with the product's shadow off, and without
    it; the last two with SSAO and bloom off, so the product changes only
    its own pixels. Everything is put back."""
    shown, paths = await _render(studio, times, width, height, out_dir / "frames", samples)
    env = await studio.call("environment.get")
    try:
        await studio.call("environment.set", ssao=False, bloom=0)
        await studio.call("component.set", entity=PRODUCT, component="MeshRenderer", fields={"cast_shadows": False})
        alone, _ = await _render(studio, times, width, height, out_dir / "mask_on", samples)
        await studio.call("component.set", entity=PRODUCT, component="MeshRenderer", fields={"visible": False})
        empty, _ = await _render(studio, times, width, height, out_dir / "mask_off", samples)
    finally:
        await studio.call("component.set", entity=PRODUCT, component="MeshRenderer",
                          fields={"visible": True, "cast_shadows": True})
        await studio.call("environment.set", ssao=env["ssao"], bloom=env["bloom"])
    return shown, paths, alone, empty


# --- One frame ----------------------------------------------------------------------------


def product_mask(alone: np.ndarray, empty: np.ndarray, box: list[float] | None) -> np.ndarray:
    """The product's pixels: where it changes the frame, inside its
    (generous) bounding box, each row filled from its leftmost to its
    rightmost pixel."""
    h, w = alone.shape[:2]
    changed = np.abs(alone.astype(int) - empty.astype(int)).max(2) > CHANGED
    if box:
        pad = 0.02
        x0, y0 = max(0, int((box[0] - pad) * w)), max(0, int((box[1] - pad) * h))
        x1, y1 = min(w, int(np.ceil((box[2] + pad) * w))), min(h, int(np.ceil((box[3] + pad) * h)))
        keep = np.zeros_like(changed)
        keep[y0:y1, x0:x1] = True
        changed &= keep
    mask = np.zeros_like(changed)
    for y in np.flatnonzero(changed.sum(1) >= 2):
        xs = np.flatnonzero(changed[y])
        mask[y, xs[0]:xs[-1] + 1] = True
    return mask


def outline(mask: np.ndarray, step: int) -> tuple[np.ndarray, np.ndarray]:
    """Points just inside and just outside the outline, (N x 2) as (y, x):
    the left and right ends of each row, and the top of each column; only
    where the outside point is in the frame and off the product."""
    h, w = mask.shape
    inside, outside = [], []
    for y in np.flatnonzero(mask.any(1)):
        xs = np.flatnonzero(mask[y])
        inside += [(y, xs[0] + step), (y, xs[-1] - step)]
        outside += [(y, xs[0] - step), (y, xs[-1] + step)]
    for x in np.flatnonzero(mask.any(0)):
        y = np.flatnonzero(mask[:, x])[0]
        inside.append((y + step, x))
        outside.append((y - step, x))
    inside, outside = np.array(inside).reshape(-1, 2), np.array(outside).reshape(-1, 2)
    in_frame = lambda p: (p[:, 0] >= 0) & (p[:, 0] < h) & (p[:, 1] >= 0) & (p[:, 1] < w)
    ok = in_frame(outside) & in_frame(inside)   # a product at the frame's edge has points past it on both sides
    inside, outside = inside[ok], outside[ok]
    ok = ~mask[outside[:, 0], outside[:, 1]] & mask[inside[:, 0], inside[:, 1]]
    return inside[ok], outside[ok]


def measure_frame(frame: Frame, shown: np.ndarray, mask: np.ndarray, colours: list[str],
                  titles: dict[str, list[float]]) -> None:
    """Fills in `frame` from its picture and the product's mask."""
    h, w = mask.shape
    if not mask.any():
        return   # out of frame, or too dark to tell from the background: flags_for says which
    rows, cols = np.flatnonzero(mask.any(1)), np.flatnonzero(mask.any(0))
    frame.fill_height = (rows[-1] - rows[0] + 1) / h
    frame.fill_width = (cols[-1] - cols[0] + 1) / w
    frame.fill_area = mask.mean()
    frame.cut_by = [edge for edge, hit in (("top", mask[0].any()), ("bottom", mask[-1].any()),
                                            ("left", mask[:, 0].any()), ("right", mask[:, -1].any())) if hit]
    ys, xs = np.nonzero(mask)
    frame.center = [xs.mean() / w, ys.mean() / h]
    frame.headroom = rows[0] / h

    lab = to_lab(shown.reshape(-1, 3).astype(float)).reshape(h, w, 3)
    inside, outside = outline(mask, max(2, round(EDGE_STEP * h)))
    if len(inside):
        d = np.linalg.norm(lab[inside[:, 0], inside[:, 1]] - lab[outside[:, 0], outside[:, 1]], axis=1)
        frame.edge_contrast = float(np.median(d))
        frame.edge_lost = float((d < LOST).mean())
    around = np.zeros_like(mask)
    pad = max(4, round(0.05 * h))
    around[max(0, rows[0] - pad):rows[-1] + pad, max(0, cols[0] - pad):cols[-1] + pad] = True
    around &= ~mask
    frame.product_l = float(np.median(lab[mask][:, 0]))
    frame.background_l = float(np.median(lab[around][:, 0])) if around.any() else frame.product_l

    pixels = shown[mask]
    frame.clipped = float((pixels.max(1) >= BLOWN).mean())
    frame.crushed = float((lab[mask][:, 0] < CRUSHED).mean())

    rendered = [c for c in _clusters(pixels, 6) if c[2] >= 0.05]
    for hexa in colours:
        target = to_lab(np.array([[int(hexa[i:i + 2], 16) for i in (1, 3, 5)]], float))[0]
        frame.palette[hexa] = round(float(min(np.linalg.norm((c[0] - target) * HUE_WEIGHTS) for c in rendered)), 1)

    for text, (x, y, bw, bh) in titles.items():
        x0, y0 = max(0, int(x * w)), max(0, int(y * h))
        x1, y1 = min(w, int(np.ceil((x + bw) * w))), min(h, int(np.ceil((y + bh) * h)))
        frame.title_overlap[text] = round(float(mask[y0:y1, x0:x1].mean()), 3) if x1 > x0 and y1 > y0 else 0.0


def flags_for(frame: Frame, is_last: bool, fade_in: float = 0.0, revealing: bool = False,
              cropping: bool = False, side_cropping: bool = False) -> list[Flag]:
    """What the numbers say is wrong in one frame. While the lights fade in
    (`fade_in` seconds) an unseen or dark one, early in a reveal one out of
    frame or cut, in a close-up (`cropping`: a shot asking for more than
    CROP) one cut while it fills the frame, and in a closer shot of a wide
    product (`side_cropping`: over SIDE_CROP) one cut only at its sides while
    it spans the frame, is the move, not a fault."""
    out, t = [], frame.time
    if not frame.fill_area:
        if not frame.bounds.get("in_view"):
            return [] if revealing else [Flag("major", "product_visibility", t, "the product is out of frame")]
        if t < fade_in:
            return []
        return [Flag("major", "lighting", t, "the product can't be seen: it's in frame but too dark to tell "
                                             "from the background")]

    def grade(value: float, limits: tuple[float, float], above: bool = True) -> str | None:
        minor, major = limits
        if (value >= major) if above else (value <= major):
            return "major"
        if (value >= minor) if above else (value <= minor):
            return "minor"
        return None

    sides_only = set(frame.cut_by) <= {"left", "right"}
    if frame.cut_by and not revealing and not (cropping and max(frame.fill_height, frame.fill_width) >= CROPPED) \
            and not (side_cropping and sides_only and frame.fill_width >= CROPPED):
        out.append(Flag("major", "product_visibility", t, f"the product is cut by the {' and '.join(frame.cut_by)} "
                                                          f"edge{'s' if len(frame.cut_by) > 1 else ''}"))
    if s := grade(frame.fill_height, SMALL, above=False):
        out.append(Flag("minor" if is_last else s, "product_visibility", t,
                        f"the product is small: {frame.fill_height:.0%} of the frame's height"))
    lit = t >= fade_in   # while the lights fade up, a dark product is the reveal
    if lit and (s := grade(frame.edge_lost, EDGE_LOST)):
        out.append(Flag(s, "lighting", t, f"{frame.edge_lost:.0%} of the product's outline merges with the "
                                          f"background (median contrast {frame.edge_contrast:.0f})"))
    if s := grade(frame.clipped, CLIPPED):
        out.append(Flag(s, "lighting", t, f"{frame.clipped:.0%} of the product's pixels are blown to white"))
    if lit and (s := grade(frame.crushed, CLIPPED)):
        out.append(Flag(s, "lighting", t, f"{frame.crushed:.0%} of the product's pixels are crushed to black"))
    for colour, distance in frame.palette.items() if lit else ():   # in the dark, colours don't show yet
        if s := grade(distance, PALETTE):
            out.append(Flag(s, "brand", t, f"{colour} isn't on the product as rendered (nearest is {distance:.0f} away)"))
    for text, share in frame.title_overlap.items():
        if s := grade(share, OVERLAP):
            out.append(Flag(s, "titles", t, f"the title {text!r} is {share:.0%} over the product"))
    return out


# --- The storyboard -------------------------------------------------------------------------


async def visible_titles(studio, sb: Storyboard, t: float, width: int, height: int) -> dict[str, list[float]]:
    """Each title shown at `t` (at least half faded in): its box as shares
    of the frame, [x, y, w, h]."""
    await studio.call("timeline.seek", t=t)
    out = {}
    for i, title in enumerate(sb.titles):
        if t >= title.start + 0.5 * title.fade:
            out[title.text] = (await studio.call("text.measure", name=f"title_{i}", width=width, height=height))["box"]
    return out


async def measure(studio, sb: Storyboard, out_dir: Path, short: int = 540, samples: int = 4,
                  colours: list[str] | None = None) -> list[ShotMeasure]:
    """Every shot of the storyboard (already built in the Studio) measured;
    the frames and masks in `out_dir`. `colours` are the brand's (hex);
    default the storyboard's own."""
    out_dir = Path(out_dir)
    width, height = frame_size(sb.aspect, short)
    moments = shot_times(sb)
    times = [t for _, t in moments]
    shown, paths, alone, empty = await _passes(studio, times, width, height, out_dir, samples)
    colours = colours or storyboard_colours(sb)
    last = sb.shots[-1].id
    reveals = {shot.id: start + REVEALING * shot.duration for start, shot in zip(sb.shot_starts(), sb.shots)
               if shot.camera.move == "reveal"}
    crops = {shot.id for shot in sb.shots if shot.camera.max_fill() > CROP}
    side_crops = {shot.id for shot in sb.shots if shot.camera.max_fill() > SIDE_CROP}

    shots: dict[str, ShotMeasure] = {}
    for (shot, t), picture, path, a, e in zip(moments, shown, paths, alone, empty):
        bounds = await studio.call("shot.bounds", entity=PRODUCT, t=t, width=width, height=height)
        frame = Frame(time=t, path=path, bounds=bounds)
        mask = product_mask(a, e, bounds.get("box"))
        measure_frame(frame, picture, mask, colours, await visible_titles(studio, sb, t, width, height))
        Image.fromarray((mask * 255).astype(np.uint8)).save(Path(path).with_suffix(".mask.png"))
        entry = shots.setdefault(shot, ShotMeasure(shot, [], []))
        entry.frames.append(frame)
        entry.flags += flags_for(frame, shot == last, sb.look.lighting.fade_in or 0.0, t < reveals.get(shot, 0.0),
                                 shot in crops, shot in side_crops)
    return list(shots.values())


def sheet(shots: list[ShotMeasure], thumb: int = 360) -> Image.Image:
    """Every frame looked at, a row per shot: the product's outline in green,
    the outline points that merge with the background in red, the flags
    written under it."""
    rows = []
    for s in shots:
        tiles = []
        for f in s.frames:
            img = Image.open(f.path).convert("RGB")
            mask = np.asarray(Image.open(Path(f.path).with_suffix(".mask.png"))) > 127
            px = np.asarray(img).copy()
            edge = mask & ~(np.roll(mask, 1, 0) & np.roll(mask, -1, 0) & np.roll(mask, 1, 1) & np.roll(mask, -1, 1))
            px[edge] = (40, 220, 90)
            if mask.any():
                lab = to_lab(px.reshape(-1, 3).astype(float)).reshape(*mask.shape, 3)
                inside, outside = outline(mask, max(2, round(EDGE_STEP * mask.shape[0])))
                lost = np.linalg.norm(lab[inside[:, 0], inside[:, 1]] - lab[outside[:, 0], outside[:, 1]], axis=1) < LOST
                for y, x in inside[lost]:
                    px[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = (240, 40, 40)
            img = Image.fromarray(px)
            img.thumbnail((thumb, thumb))
            tile = Image.new("RGB", (img.width, img.height + 70), (20, 20, 22))
            tile.paste(img)
            notes = [f"{s.shot} t={f.time:g}  fill {f.fill_height:.0%}  edge lost {f.edge_lost:.0%}  clip {f.clipped:.0%}"]
            notes += [f"{x.severity}: {x.problem}" for x in s.flags if x.time == f.time][:3]
            ImageDraw.Draw(tile).text((4, img.height + 4), "\n".join(n[:64] for n in notes), fill=(230, 230, 230))
            tiles.append(tile)
        row = Image.new("RGB", (sum(t.width for t in tiles), max(t.height for t in tiles)), (20, 20, 22))
        x = 0
        for t in tiles:
            row.paste(t, (x, 0))
            x += t.width
        rows.append(row)
    out = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (20, 20, 22))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    return out
