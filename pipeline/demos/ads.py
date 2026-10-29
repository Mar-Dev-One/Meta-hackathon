"""Ads written by hand as storyboards (pipeline/schemas): no AI, the same
data the director agent writes, built with the same builder
(pipeline.studio.build). Test footage, fallback demos, and examples of a
good storyboard.

    python -m pipeline.demos.ads                      # every ad, each a run in runs/; the video also in pipeline/demos/out/<name>.mp4
    python -m pipeline.demos.ads fizzo kora           # some of them
    python -m pipeline.demos.ads --preview            # a few frames of each as PNGs, to check the look first
    python -m pipeline.demos.ads --list
    python -m pipeline.demos.ads --export             # each storyboard as JSON in pipeline/demos/out/storyboards

Every brand here is made up. Labels are drawn with Pillow from `label_art`;
the brand analyst will later cut them from product photos.
"""

import argparse
import asyncio
import json
import shutil
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.runs import Run
from pipeline.schemas import (Backdrop, CameraMove, Environment, Label, Lighting, Look, PartLook, Pedestal, Product,
                              Shot, Storyboard, Title, Track)
from pipeline.studio import Studio, build, preview, render

OUT = Path(__file__).resolve().parent / "out"
FONTS = Path("C:/Windows/Fonts")   # system fonts for the label artwork (the titles use the Studio's OFL fonts)
LABEL = "label.png"                # replaced by the drawn label's path when the ad is built

# --- Labels ------------------------------------------------------------------------------


def draw_label(path: Path, size, background=(255, 255, 255), lines=(), border=None, radius=60, gradient=None) -> Path:
    """A label image: a background (optionally a vertical gradient), an
    optional inset border, and centred lines of (text, font file, px size,
    y px, colour). Transparent outside the rounded corners."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if gradient:
        top, bottom = gradient
        fill = Image.new("RGBA", (w, h))
        px = fill.load()
        for y in range(h):
            c = tuple(round(a + (b - a) * y / (h - 1)) for a, b in zip(top, bottom)) + (255,)
            for x in range(w):
                px[x, y] = c
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        img.paste(fill, (0, 0), mask)
    else:
        ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=tuple(background) + (255,))
    d = ImageDraw.Draw(img)
    if border:
        d.rounded_rectangle([30, 30, w - 31, h - 31], radius=max(radius - 20, 0), outline=tuple(border) + (255,), width=6)
    for text, font, px, y, color in lines:
        f = ImageFont.truetype(str(FONTS / font), px)
        d.text(((w - d.textlength(text, font=f)) / 2, y), text, font=f, fill=tuple(color) + (255,))
    img.save(path)
    return path


# --- The ads ---------------------------------------------------------------------------------

DARK = Environment()   # the defaults: HDRI for reflections only, dim ambient, AgX

ADS: dict[str, dict] = {
    "noctis": dict(
        storyboard=Storyboard(
            title="Noctis: Noir Absolu", brief="Luxury perfume ad, dark and moody, 13 seconds.",
            style="dark and moody luxury",
            look=Look(environment=DARK, backdrop=Backdrop(color="#0A0A0C"),
                      pedestal=Pedestal(width=0.32, height=0.18, color="#0E0E10"),
                      lighting=Lighting(preset="rim_dark", fade_in=2.5, glow=2)),
            product=Product(template="perfume",
                            parts={"body": PartLook(color="#F4EEF0", transmission=1, roughness=0.04,
                                                      attenuation_color="#8C2A5A", attenuation_distance=0.08),
                                   "cap": PartLook(color="#D4AF6A", roughness=0.18)},
                            label=Label(image=LABEL, arc=110)),
            shots=[
                Shot(id="s1", intent="the bottle emerges from darkness as the rim lights rise", duration=3,
                     camera=CameraMove(move="reveal", fill=0.5, azimuth=-15, elevation=4, **{"from": "above"})),
                Shot(id="s2", intent="a low orbit: the rims slide across the glass", duration=4,
                     camera=CameraMove(move="orbit", azimuth=-60, to_azimuth=10, elevation=3, fill=0.6)),
                Shot(id="s3", intent="push in on the label and cap", duration=3,
                     camera=CameraMove(move="dolly", azimuth=12, elevation=8, from_fill=0.55, to_fill=0.95, aperture=2.8)),
                Shot(id="s4", intent="the hero: still, the name below", duration=3,
                     camera=CameraMove(move="static", azimuth=0, elevation=2, fill=0.45, aperture=2.8)),
            ],
            titles=[Title(text="NOCTIS", start=10.6, font="serif", size=0.075, y=0.83, color="#ECE4D2", tracking=0.25),
                    Title(text="NOIR ABSOLU", start=11.0, font="sans", size=0.026, y=0.905, color="#C9A45C", tracking=0.3)],
        ),
        label_art=dict(size=(1200, 800), background=(236, 226, 206), border=(160, 122, 62),
                       lines=[("N O C T I S", "georgia.ttf", 170, 250, (30, 22, 18)),
                              ("NOIR ABSOLU", "georgia.ttf", 64, 560, (120, 90, 50))]),
    ),

    "fizzo": dict(
        storyboard=Storyboard(
            title="Fizzo: Sparkling Citrus", brief="Sparkling drink, bold and energetic, fast cuts, 8 seconds.",
            style="bold, neon, energetic",
            look=Look(environment=Environment(bloom=0.14), background=[0.01, 0.003, 0.015],
                      backdrop=Backdrop(color="#140A1C", roughness=0.5),
                      pedestal=Pedestal(width=0.2, height=0.12, color="#1A1020", roughness=0.4),
                      lighting=Lighting(preset="neon_dual", intensity=1.2)),
            # The label wraps all the way round: the image is wide, its seam at the back.
            product=Product(template="can", parts={"body": PartLook(color="#D8D8DE", roughness=0.18, clearcoat=1,
                                                                    clearcoat_roughness=0.04)},
                            label=Label(image=LABEL, arc=360, **{"from": 0.014}, to=0.104)),
            shots=[
                Shot(id="s1", intent="whip round the spinning can", duration=1.6,
                     camera=CameraMove(move="orbit", azimuth=-80, to_azimuth=0, elevation=10, fill=0.55, ease="out")),
                Shot(id="s2", intent="punch in from below", duration=1.4,
                     camera=CameraMove(move="dolly", azimuth=25, elevation=-5, from_fill=0.6, to_fill=1.0, ease="out")),
                Shot(id="s3", intent="sweep up over the top", duration=1.5,
                     camera=CameraMove(move="crane", from_elevation=-15, to_elevation=40, fill=0.65)),
                Shot(id="s4", intent="slide past", duration=1.2,
                     camera=CameraMove(move="truck", fill=0.8, elevation=5, ease="out")),
                Shot(id="s5", intent="the hero: the can settles facing front, the name below", duration=2.3,
                     camera=CameraMove(move="static", elevation=6, fill=0.5)),
            ],
            titles=[Title(text="FIZZO", start=6.0, font="condensed", size=0.13, y=0.82, color="#FF5AB0", tracking=0.04, fade=0.25),
                    Title(text="ZERO SUGAR. ALL SPARK.", start=6.3, font="sans_bold", size=0.03, y=0.93, color="#FFFFFF",
                          tracking=0.12, fade=0.25)],
            # The can spins, settling with its label to the front.
            tracks=[Track(entity="product", component="Transform", field="rotation_deg",
                          keys=[{"t": 0, "value": [0, -300, 0], "ease": "out"}, {"t": 6.5, "value": [0, 0, 0]}])],
        ),
        label_art=dict(size=(2400, 800), radius=0, gradient=((255, 60, 140), (255, 150, 40)),
                       lines=[("FIZZO", "arialbd.ttf", 330, 150, (255, 255, 255)),
                              ("SPARKLING  CITRUS", "bahnschrift.ttf", 90, 560, (255, 240, 220))]),
    ),

    "kora": dict(
        storyboard=Storyboard(
            title="Kora: Restoring Cream", brief="Skincare, clean and minimal, bright, 12 seconds.",
            style="clean, minimal, bright",
            look=Look(environment=Environment(ambient_strength=0.6, bloom=0.03, tonemap="neutral"),
                      background=[0.75, 0.73, 0.70], backdrop=Backdrop(color="#E7E3DD", roughness=0.85),
                      pedestal=Pedestal(width=0.2, height=0.1, color="#F1EEE9", roughness=0.7),
                      lighting=Lighting(preset="high_key")),
            product=Product(template="jar",
                            parts={"body": PartLook(color="#EFE8DE", roughness=0.3),
                                   "lid": PartLook(color="#C9A78A", metallic=0.85, roughness=0.3)},
                            label=Label(image=LABEL, arc=120)),
            shots=[
                Shot(id="s1", intent="calm establishing view from above", duration=3,
                     camera=CameraMove(move="static", azimuth=-25, elevation=22, fill=0.55)),
                Shot(id="s2", intent="slow push in to the label", duration=3,
                     camera=CameraMove(move="dolly", azimuth=10, elevation=12, from_fill=0.6, to_fill=1.05)),
                Shot(id="s3", intent="gentle orbit over the lid", duration=3,
                     camera=CameraMove(move="orbit", azimuth=-30, to_azimuth=20, elevation=28, fill=0.75)),
                Shot(id="s4", intent="the hero, the name below", duration=3,
                     camera=CameraMove(move="static", azimuth=0, elevation=10, fill=0.62, aperture=4)),
            ],
            titles=[Title(text="KORA", start=9.4, font="serif", size=0.07, y=0.82, color="#3C342E", tracking=0.2),
                    Title(text="Skin, simply.", start=9.8, font="script", size=0.045, y=0.9, color="#8C7864")],
        ),
        label_art=dict(size=(1200, 700), background=(250, 247, 242), radius=40,
                       lines=[("KORA", "georgia.ttf", 200, 170, (60, 52, 46)),
                              ("RESTORING CREAM", "arial.ttf", 60, 450, (140, 120, 100))]),
    ),

    "verde": dict(
        storyboard=Storyboard(
            title="Verde: Extra Virgin Olive Oil", brief="Extra virgin olive oil, warm and natural, 10 seconds.",
            style="warm, natural, earthy",
            look=Look(environment=Environment(ambient_strength=0.12, exposure=1.1), background=[0.03, 0.02, 0.012],
                      backdrop=Backdrop(color="#2A1D13", roughness=0.7),
                      pedestal=Pedestal(width=0.34, height=0.08, color="#5B3D25", roughness=0.6),
                      lighting=Lighting(preset="top_soft", warmth=0.6, glow=1.5)),
            product=Product(template="bottle",
                            parts={"body": PartLook(color="#C9DDB0", transmission=1, roughness=0.05,
                                                      attenuation_color="#7C8C24", attenuation_distance=0.08),
                                   "cap": PartLook(color="#C9A45C", metallic=1, roughness=0.3)},
                            label=Label(image=LABEL, arc=100)),
            shots=[
                Shot(id="s1", intent="crane down from above onto the bottle", duration=3.5,
                     camera=CameraMove(move="crane", from_elevation=50, to_elevation=8, fill=0.65)),
                Shot(id="s2", intent="orbit through the warm light", duration=3.5,
                     camera=CameraMove(move="orbit", azimuth=40, to_azimuth=-20, elevation=5, fill=0.8)),
                Shot(id="s3", intent="the hero, the name below", duration=3,
                     camera=CameraMove(move="static", azimuth=-8, elevation=4, fill=0.66, aperture=4)),
            ],
            titles=[Title(text="VERDE", start=7.3, font="serif", size=0.075, y=0.83, color="#E8DCB8", tracking=0.2),
                    Title(text="Pressed the day it's picked", start=7.7, font="serif", size=0.032, y=0.915, color="#D9B86A")],
        ),
        label_art=dict(size=(1000, 900), background=(242, 234, 214), border=(90, 110, 50), radius=30,
                       lines=[("VERDE", "georgia.ttf", 190, 180, (60, 80, 30)),
                              ("EXTRA VIRGIN", "georgia.ttf", 70, 470, (90, 70, 40)),
                              ("OLIVE OIL", "georgia.ttf", 70, 570, (90, 70, 40))]),
    ),

    "lumen": dict(
        storyboard=Storyboard(
            title="Lumen: Vitamin C Serum", brief="Vitamin C serum, warm and glowing, 10 seconds.",
            style="warm, glowing, premium",
            look=Look(environment=Environment(bloom=0.12), background=[0.012, 0.007, 0.004],
                      backdrop=Backdrop(color="#120C08"),
                      pedestal=Pedestal(width=0.22, height=0.16, color="#0B0806", roughness=0.9),
                      lighting=Lighting(preset="rim_dark", warmth=0.5, intensity=1.2, fade_in=2.0, glow=2)),
            product=Product(template="dropper", parts={"body": PartLook(color="#FFF1E0", transmission=1, roughness=0.04,
                                                                        attenuation_color="#C46A12",
                                                                        attenuation_distance=0.03)},
                            label=Label(image=LABEL, arc=110)),
            shots=[
                Shot(id="s1", intent="zoom in as the glow rises", duration=3,
                     camera=CameraMove(move="zoom", from_fov=50, to_fov=28, azimuth=-20, elevation=6, fill=0.55)),
                Shot(id="s2", intent="orbit: light through the amber glass", duration=4,
                     camera=CameraMove(move="orbit", azimuth=-70, to_azimuth=30, elevation=4, fill=0.65)),
                Shot(id="s3", intent="the hero, the name below", duration=3,
                     camera=CameraMove(move="static", azimuth=0, elevation=3, fill=0.48, aperture=2.8)),
            ],
            titles=[Title(text="LUMEN", start=7.3, font="sans_bold", size=0.075, y=0.83, color="#F2A24A", tracking=0.18),
                    Title(text="Glow, bottled.", start=7.7, font="sans", size=0.03, y=0.915, color="#E8D8C0", tracking=0.05)],
        ),
        label_art=dict(size=(1000, 900), background=(250, 244, 232), radius=30,
                       lines=[("LUMEN", "arialbd.ttf", 190, 200, (200, 100, 20)),
                              ("VITAMIN C SERUM", "arial.ttf", 64, 500, (80, 60, 40)),
                              ("30 ml", "arial.ttf", 54, 640, (120, 100, 80))]),
    ),
}

# --- Rendering -----------------------------------------------------------------------------------


def storyboard_for(name: str) -> Storyboard:
    """The ad's storyboard with its label drawn and pointed to."""
    ad = ADS[name]
    sb: Storyboard = ad["storyboard"]
    image = draw_label(OUT / f"{name}_label.png", **ad["label_art"])
    return sb.model_copy(update={"product": sb.product.model_copy(
        update={"label": sb.product.label.model_copy(update={"image": str(image)})})})


async def make(studio: Studio, name: str, preview_only: bool, short: int, samples: int) -> Path:
    """One ad as a run (pipeline/runs.py): its inputs, storyboard, every
    Studio command, and its frames or video, in runs/<time>-<name>/. Returns
    the run's folder."""
    with Run.create(f"{name}{'-preview' if preview_only else ''}") as run:
        run.watch(studio)
        sb = storyboard_for(name)
        run.event("brief", text=sb.brief, style=sb.style)
        label = run.add_file(sb.product.label.image, "inputs/label.png")
        sb = sb.model_copy(update={"product": sb.product.model_copy(
            update={"label": sb.product.label.model_copy(update={"image": str(label)})})})
        run.output("storyboard", run.save_json("storyboard.json", sb))

        run.event("build", shots=len(sb.shots), duration=sb.duration)
        await build(studio, sb)
        if preview_only:
            await preview(studio, run, sb)
            return run.root
        final = await render(studio, run, sb, name, short=short, samples=samples)
        shutil.copyfile(final, OUT / f"{name}.mp4")   # the latest of each, where it's easy to find
        return run.root


async def run(names: list[str], preview_only: bool, short: int, samples: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with Studio() as studio:
        for name in names:
            began = time.time()
            folder = await make(studio, name, preview_only, short, samples)
            print(f"{name}: {time.time() - began:.0f}s -> {folder}")


def export(names: list[str]) -> None:
    folder = OUT / "storyboards"
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = folder / f"{name}.json"
        path.write_text(json.dumps(ADS[name]["storyboard"].model_dump(by_alias=True, exclude_none=True), indent=2),
                        encoding="utf-8")
        print(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
    parser.add_argument("--preview", action="store_true", help="a few frames of each as PNGs instead of videos")
    parser.add_argument("--list", action="store_true", help="list the ads and stop")
    parser.add_argument("--export", action="store_true", help="write each storyboard as JSON and stop")
    parser.add_argument("--size", type=int, default=1080, help="the frame's shorter side in pixels (default 1080)")
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args()
    unknown = [a for a in args.ads if a not in ADS]
    if unknown:
        parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")
    names = args.ads or list(ADS)
    if args.list:
        for name, ad in ADS.items():
            sb = ad["storyboard"]
            print(f"{name:8} {sb.duration:>5.1f} s  {sb.style}")
    elif args.export:
        export(names)
    else:
        asyncio.run(run(names, args.preview, args.size, args.samples))
