"""The brand analyst, whole: a product photo in, a BrandProfile out, and
everything it saw kept in the run.

    with Run.create("aurelle") as run:
        a = analyse(run, "Assets/photos/aurelle_perfume.png", "perfume bottle")
        a.profile                      # the BrandProfile; a.profile.product() is the storyboard's product
        frames = await turntable_frames(studio, run, a.profile)
        contact_sheet(a, frames).save(run.path("contact_sheet.png"))

It segments the photo (SAM 3.1), measures the palette, reads the materials
and the brand (Muse Spark), traces the shape, cuts the label, and writes
brand_profile.json, masks.png, outline.png and label.png into the run.

    python -m pipeline.agents.analyst Assets/photos/*.png --category "perfume bottle" ... [--video]
"""

import textwrap
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.encode import finish
from pipeline.runs import Run
from pipeline.schemas import BrandProfile, Label, Storyboard, Swatch
from pipeline.schemas.storyboard import Backdrop, CameraMove, Environment, Key, Lighting, Look, Shot, Track
from pipeline.studio import PRODUCT, build

from .label import CutLabel, unroll
from .materials import Reading, dress, read
from .palette import palette, strip
from .profile import Traced, outline, trace
from .segment import Segmentation, overlay, segment


@dataclass
class Analysis:
    profile: BrandProfile
    seg: Segmentation
    swatches: list[Swatch]
    reading: Reading
    traced: Traced
    cut: CutLabel | None


def analyse(run: Run, photo: Path | str, category: str = "product") -> Analysis:
    """The BrandProfile of the product in `photo` (`category` helps SAM find
    it: "perfume bottle"), with what it was made from."""
    photo = Path(photo)
    run.event("analyse", photo=photo.name, category=category)
    kept = run.add_file(photo, "inputs/" + photo.name)

    seg = segment(kept, category)
    run.event("segmented", **{r.name: list(r.box) for r in [seg.product, *seg.parts.values()]})
    overlay(seg).save(run.path("masks.png"))

    swatches = palette(seg)
    reading = read(seg, swatches, category)
    run.event("read", brand=reading.brand, category=reading.category, height=reading.height)

    traced = trace(seg, reading.height)
    traced.parts = dress(traced.parts, reading)
    outline(seg, traced).save(run.path("outline.png"))

    cut = unroll(seg, traced)
    label = None
    if cut:
        cut.image.save(run.path("label.png"))
        label = Label.model_validate(cut.command(str(run.root / "label.png")))

    profile = BrandProfile(
        brand=reading.brand, product_name=reading.product_name, category=reading.category, template=None,
        height=reading.height, profile_parts=traced.parts, materials=reading.materials, palette=swatches,
        typography=reading.typography, mood=reading.mood, do_not=reading.do_not, label=label, photos=[str(kept)])
    run.output("brand_profile", run.save_json("brand_profile.json", profile))
    return Analysis(profile, seg, swatches, reading, traced, cut)


# --- Seeing it --------------------------------------------------------------------------------

TURN = 6.0                       # seconds for a full turn
ANGLES = [0, 45, 90]             # the turntable's frames on the contact sheet, degrees from the front


def turntable(profile: BrandProfile, seconds: float = TURN) -> Storyboard:
    """The product turning once in front of a still camera on a plain light
    set (the camera stays where the set is), front at the middle."""
    return Storyboard(
        title=f"{profile.brand or 'product'} turntable", brief="the brand analyst's product, all the way round",
        style="clean light studio", aspect="1:1",
        look=Look(environment=Environment(ambient_strength=0.6, bloom=0.03, tonemap="neutral"),
                  background=[0.75, 0.75, 0.75], backdrop=Backdrop(color="#DADADA", roughness=0.9), pedestal=None,
                  lighting=Lighting(preset="high_key")),
        product=profile.product(),
        shots=[Shot(id="s1", intent="the product turning, all the way round", duration=seconds,
                    camera=CameraMove(move="static", elevation=5, fill=0.75, fov_degrees=25))],
        tracks=[Track(entity=PRODUCT, component="Transform", field="rotation_deg",
                      keys=[Key(t=0, value=[0, -180, 0]), Key(t=seconds, value=[0, 180, 0])])])


def turn_time(angle: float, seconds: float = TURN) -> float:
    return round((angle + 180) / 360 * seconds, 3)


async def turntable_frames(studio, run: Run, profile: BrandProfile, size: int = 720) -> list[Image.Image]:
    """The turntable at ANGLES, as frames saved in the run's frames/."""
    sb = turntable(profile)
    run.save_json("turntable.json", sb)
    await build(studio, sb)
    result = await studio.call("shot.preview", times=[turn_time(a) for a in ANGLES], width=size, height=size,
                               out_dir=str(run.folder("frames")))
    return [Image.open(f["path"]).convert("RGB") for f in result["frames"]]


async def turntable_video(studio, run: Run, profile: BrandProfile, size: int = 720) -> Path:
    """The whole turn as final/turntable.mp4 (the scene must be built: turntable_frames)."""
    raw = run.path("final", "raw.mp4")
    await studio.call("shot.render", video=str(raw), end=TURN - 1e-3, fps=30, width=size, height=size, samples=8)
    video = finish(raw, run.path("final", "turntable.mp4"), fade_in=0.3, fade_out=0.3)
    raw.unlink(missing_ok=True)
    run.output("turntable", video)
    return video


def _fit(image: Image.Image, height: int) -> Image.Image:
    return image.resize((max(1, round(image.width * height / image.height)), height), Image.Resampling.LANCZOS)


def _around(image: Image.Image, box: tuple[int, int, int, int], margin: float = 0.08) -> Image.Image:
    """`image` cut to a square around `box`, with a margin; past the
    image's edges, its corner colour (the photo's background)."""
    x0, y0, x1, y1 = box
    side = round(max(x1 - x0, y1 - y0) * (1 + 2 * margin))
    left, top = round((x0 + x1 - side) / 2), round((y0 + y1 - side) / 2)
    out = Image.new("RGB", (side, side), image.getpixel((2, 2)))
    out.paste(image.crop((max(left, 0), max(top, 0), min(left + side, image.width), min(top + side, image.height))),
              (max(-left, 0), max(-top, 0)))
    return out


def _checker(size: tuple[int, int], cell: int = 12) -> Image.Image:
    out = Image.new("RGB", size, (235, 235, 235))
    draw = ImageDraw.Draw(out)
    for y in range(0, size[1], cell):
        for x in range((y // cell) % 2 * cell, size[0], 2 * cell):
            draw.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(205, 205, 205))
    return out


def contact_sheet(a: Analysis, frames: list[Image.Image], tile: int = 520) -> Image.Image:
    """One picture of the analysis: the photo with its masks, the traced
    profile, the turntable; under them the label, the palette and what
    Spark read."""
    box = a.seg.product.box
    top = [_around(overlay(a.seg), box), _around(outline(a.seg, a.traced), box)] + frames
    top = [_fit(t, tile) for t in top]
    gap = 10
    width = sum(t.width for t in top) + gap * (len(top) - 1)

    font = ImageFont.load_default(size=20)
    small = ImageFont.load_default(size=17)
    p = a.profile
    lines = [f"{p.brand}{' ' + p.product_name if p.product_name else ''}: {p.category}, {p.height * 100:.0f} cm",
             *(f"{m.name}: {m.looks_like} ({m.color}, metal {m.metallic:g}, rough {m.roughness:g}"
               f"{f', opacity {m.opacity:g}' if m.opacity < 1 else ''})" for m in p.materials),
             f"type: {p.typography.font}, {p.typography.case} case, tracking {p.typography.tracking:g}",
             f"mood: {', '.join(p.mood)}",
             *textwrap.wrap(f"do not: {'; '.join(p.do_not)}", 70)]
    text_w = 760
    label_h = 200
    palette_h = 90
    bottom_h = max(label_h + gap + palette_h, 28 * len(lines) + 20)

    out = Image.new("RGB", (max(width, text_w + 400), tile + gap + bottom_h), (255, 255, 255))
    x = 0
    for t in top:
        out.paste(t, (x, 0))
        x += t.width + gap
    y = tile + gap
    left_w = out.width - text_w - gap
    if a.cut:
        label = _fit(a.cut.image, label_h)
        if label.width > left_w:
            label = label.resize((left_w, round(label.height * left_w / label.width)))
        back = _checker(label.size)
        back.paste(label, (0, 0), label)
        out.paste(back, (0, y))
    out.paste(strip(a.swatches, left_w, palette_h), (0, y + label_h + gap))
    draw = ImageDraw.Draw(out)
    for i, line in enumerate(lines):
        draw.text((left_w + gap + 10, y + 6 + 28 * i), line, fill=(20, 20, 20), font=font if i == 0 else small)
    return out
