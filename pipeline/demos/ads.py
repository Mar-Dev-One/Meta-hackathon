"""Ads written by hand: no AI, just Studio commands from a spec per ad. Test
footage for the pipeline, a fallback demo, and the shape of what the
director agent will write for itself (a scene, a shot list, titles).

    python -m pipeline.demos.ads                      # every ad: pipeline/demos/out/<name>.mp4
    python -m pipeline.demos.ads fizzo kora           # some of them
    python -m pipeline.demos.ads --preview            # a few frames of each as PNGs, to check the look first
    python -m pipeline.demos.ads --list

Every brand here is made up. Labels are drawn with Pillow; the brand analyst
will later take them from product photos.
"""

import argparse
import asyncio
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.encode import Title, finish
from pipeline.studio import Studio

OUT = Path(__file__).resolve().parent / "out"
FONTS = Path("C:/Windows/Fonts")   # system fonts for these tests; shipped demos use OFL fonts

# --- Labels ------------------------------------------------------------------------------


def draw_label(path: Path, size, background, lines, border=None, radius=60, gradient=None) -> Path:
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

DARK_ENV = dict(hdri="hdri/citrus_orchard_road_puresky_4k.hdr", use_ibl=True, show_skybox=False,
                ambient_strength=0.06, exposure=1.0, bloom=0.08, tonemap="agx", ssao=True)

ADS = {
    "noctis": dict(
        about="luxury perfume, dark and moody",
        environment=DARK_ENV, clear_color=[0.004, 0.004, 0.006],
        backdrop=dict(color="#0a0a0c", roughness=0.6),
        pedestal=dict(width=0.32, height=0.22, color="#0e0e10", roughness=0.85),
        product=dict(template="perfume", parts={"body": {"color": "#4a1030", "opacity": 0.92, "roughness": 0.04},
                                                "cap": {"color": "#d4af6a", "roughness": 0.18}}),
        label=dict(arc=110, size=(1200, 800), background=(236, 226, 206), border=(160, 122, 62),
                   lines=[("N O C T I S", "georgia.ttf", 170, 250, (30, 22, 18)),
                          ("NOIR ABSOLU", "georgia.ttf", 64, 560, (120, 90, 50))]),
        lighting=dict(name="rim_dark"),
        fade_in_lights=(["light_rim_left", "light_rim_right"], 2.5),
        shots=[
            dict(move="reveal", start=0, duration=3, fill=0.5, azimuth=-15, elevation=4, **{"from": "above"}),
            dict(move="orbit", start=3, duration=4, azimuth=-60, to_azimuth=10, elevation=3, fill=0.6),
            dict(move="dolly", start=7, duration=3, azimuth=12, elevation=8, from_fill=0.55, to_fill=0.95),
            dict(move="static", start=10, duration=3, azimuth=0, elevation=2, fill=0.45),
        ],
        titles=[Title("NOCTIS", 10.6, 13.0, size=0.075, y=0.83, tracking=3),
                Title("NOIR ABSOLU", 11.0, 13.0, size=0.028, y=0.905, color="#c9a45c", tracking=2)],
    ),

    "fizzo": dict(
        about="sparkling drink, bold and energetic, fast cuts",
        environment={**DARK_ENV, "bloom": 0.14}, clear_color=[0.01, 0.003, 0.015],
        backdrop=dict(color="#140a1c", roughness=0.5),
        pedestal=dict(width=0.2, height=0.12, color="#1a1020", roughness=0.4),
        product=dict(template="can", parts={"body": {"color": "#d8d8de", "roughness": 0.18}}),
        # Wraps all the way round: the image is wide, its seam at the back.
        label=dict(arc=360, from_=0.014, to=0.104, size=(2400, 800), radius=0, gradient=((255, 60, 140), (255, 150, 40)),
                   lines=[("FIZZO", "arialbd.ttf", 330, 150, (255, 255, 255)),
                          ("SPARKLING  CITRUS", "bahnschrift.ttf", 90, 560, (255, 240, 220))]),
        lighting=dict(name="neon_dual", intensity=1.2),
        # The can spins the whole time.
        tracks=[dict(entity="product", component="Transform", field="rotation_deg",
                     keys=[{"t": 0, "value": [0, -300, 0], "ease": "out"}, {"t": 6.5, "value": [0, 0, 0]}])],
        shots=[
            dict(move="orbit", start=0, duration=1.6, azimuth=-80, to_azimuth=0, elevation=10, fill=0.55, ease="out"),
            dict(move="dolly", start=1.6, duration=1.4, azimuth=25, elevation=-5, from_fill=0.6, to_fill=1.0, ease="out"),
            dict(move="crane", start=3.0, duration=1.5, from_elevation=-15, to_elevation=40, fill=0.65, ease="in_out"),
            dict(move="truck", start=4.5, duration=1.2, fill=0.8, elevation=5, ease="out"),
            dict(move="static", start=5.7, duration=2.3, elevation=6, fill=0.5),
        ],
        titles=[Title("FIZZO", 6.0, 8.0, size=0.11, y=0.84, color="#ff5ab0", fade=0.25, font=FONTS / "arialbd.ttf"),
                Title("ZERO SUGAR. ALL SPARK.", 6.3, 8.0, size=0.032, y=0.93, fade=0.25, tracking=1,
                      font=FONTS / "bahnschrift.ttf")],
    ),

    "kora": dict(
        about="skincare, clean and minimal, bright",
        environment=dict(hdri="hdri/citrus_orchard_road_puresky_4k.hdr", use_ibl=True, show_skybox=False,
                         ambient_strength=0.6, exposure=1.0, bloom=0.03, tonemap="neutral", ssao=True),
        clear_color=[0.75, 0.73, 0.70],
        backdrop=dict(color="#e7e3dd", roughness=0.85),
        pedestal=dict(width=0.2, height=0.1, color="#f1eee9", roughness=0.7),
        product=dict(template="jar", parts={"body": {"color": "#efe8de", "roughness": 0.3},
                                            "lid": {"color": "#c9a78a", "metallic": 0.85, "roughness": 0.3}}),
        label=dict(arc=120, size=(1200, 700), background=(250, 247, 242), radius=40,
                   lines=[("KORA", "georgia.ttf", 200, 170, (60, 52, 46)),
                          ("RESTORING CREAM", "arial.ttf", 60, 450, (140, 120, 100))]),
        lighting=dict(name="high_key"),
        shots=[
            dict(move="static", start=0, duration=3, azimuth=-25, elevation=22, fill=0.55),
            dict(move="dolly", start=3, duration=3, azimuth=10, elevation=12, from_fill=0.6, to_fill=1.05),
            dict(move="orbit", start=6, duration=3, azimuth=-30, to_azimuth=20, elevation=28, fill=0.75),
            dict(move="static", start=9, duration=3, azimuth=0, elevation=10, fill=0.62),
        ],
        titles=[Title("KORA", 9.4, 12.0, size=0.07, y=0.82, color="#3c342e", tracking=2),
                Title("Skin, simply.", 9.8, 12.0, size=0.032, y=0.9, color="#8c7864")],
    ),

    "verde": dict(
        about="extra virgin olive oil, warm and natural",
        environment={**DARK_ENV, "ambient_strength": 0.12, "exposure": 1.1}, clear_color=[0.03, 0.02, 0.012],
        backdrop=dict(color="#2a1d13", roughness=0.7),
        pedestal=dict(width=0.34, height=0.08, color="#5b3d25", roughness=0.6),
        product=dict(template="bottle", parts={"body": {"color": "#3f5a1c", "opacity": 0.93, "roughness": 0.05},
                                               "cap": {"color": "#c9a45c", "metallic": 1, "roughness": 0.3}}),
        label=dict(arc=100, size=(1000, 900), background=(242, 234, 214), border=(90, 110, 50), radius=30,
                   lines=[("VERDE", "georgia.ttf", 190, 180, (60, 80, 30)),
                          ("EXTRA VIRGIN", "georgia.ttf", 70, 470, (90, 70, 40)),
                          ("OLIVE OIL", "georgia.ttf", 70, 570, (90, 70, 40))]),
        lighting=dict(name="top_soft", warmth=0.6),
        shots=[
            dict(move="crane", start=0, duration=3.5, from_elevation=50, to_elevation=8, fill=0.65),
            dict(move="orbit", start=3.5, duration=3.5, azimuth=40, to_azimuth=-20, elevation=5, fill=0.8),
            dict(move="static", start=7, duration=3, azimuth=-8, elevation=4, fill=0.66),
        ],
        titles=[Title("VERDE", 7.3, 10.0, size=0.075, y=0.85, color="#e8dcb8", tracking=2),
                Title("Pressed the day it's picked", 7.7, 10.0, size=0.03, y=0.92, color="#c9a45c")],
    ),

    "lumen": dict(
        about="vitamin C serum, warm and glowing",
        environment={**DARK_ENV, "bloom": 0.12}, clear_color=[0.012, 0.007, 0.004],
        backdrop=dict(color="#120c08", roughness=0.6),
        pedestal=dict(width=0.22, height=0.16, color="#0b0806", roughness=0.9),
        product=dict(template="dropper", parts={"body": {"color": "#c46a12", "opacity": 0.9, "roughness": 0.04}}),
        label=dict(arc=110, size=(1000, 900), background=(250, 244, 232), radius=30,
                   lines=[("LUMEN", "arialbd.ttf", 190, 200, (200, 100, 20)),
                          ("VITAMIN C SERUM", "arial.ttf", 64, 500, (80, 60, 40)),
                          ("30 ml", "arial.ttf", 54, 640, (120, 100, 80))]),
        lighting=dict(name="rim_dark", warmth=0.5, intensity=1.2),
        fade_in_lights=(["light_rim_left", "light_rim_right", "light_key"], 2.0),
        shots=[
            dict(move="zoom", start=0, duration=3, from_fov=50, to_fov=28, azimuth=-20, elevation=6, fill=0.55),
            dict(move="orbit", start=3, duration=4, azimuth=-70, to_azimuth=30, elevation=4, fill=0.65),
            dict(move="static", start=7, duration=3, azimuth=0, elevation=3, fill=0.48),
        ],
        titles=[Title("LUMEN", 7.3, 10.0, size=0.075, y=0.84, color="#f2a24a", tracking=2,
                      font=FONTS / "arialbd.ttf"),
                Title("Glow, bottled.", 7.7, 10.0, size=0.032, y=0.92, color="#e8d8c0")],
    ),
}

# --- Building and rendering --------------------------------------------------------------------


async def build(studio: Studio, name: str, ad: dict) -> float:
    """Sets up the ad's scene and timeline; returns its length in seconds."""
    await studio.call("studio.reset")
    await studio.call("environment.set", **ad["environment"])
    await studio.call("render.set", antialiasing="taa", clear_color=ad["clear_color"])

    await studio.call("backdrop.create", kind="cyclorama", **ad["backdrop"])
    top = 0.0
    if ad.get("pedestal"):
        await studio.call("backdrop.create", kind="pedestal", **ad["pedestal"])
        top = ad["pedestal"]["height"]

    label = dict(ad["label"])
    image = draw_label(OUT / f"{name}_label.png", label.pop("size"), label.pop("background", (255, 255, 255)),
                       label.pop("lines"), border=label.pop("border", None), radius=label.pop("radius", 60),
                       gradient=label.pop("gradient", None))
    if "from_" in label:
        label["from"] = label.pop("from_")
    await studio.call("product.create", name="product", position=[0, top, 0], label={"image": str(image), **label},
                      **ad["product"])

    lights = await studio.call("lighting.preset", subject="product", **ad["lighting"])
    intensity = {light["entity"]: light["intensity"] for light in lights["lights"]}

    for shot in ad["shots"]:
        await studio.call("camera.move", subject="product", **shot)
    if ad.get("fade_in_lights"):
        names, until = ad["fade_in_lights"]
        for light in names:
            await studio.call("timeline.set_track", entity=light, component="Light", field="intensity",
                              keys=[{"t": 0, "value": 0.0, "ease": "in"}, {"t": until, "value": intensity[light]}])
    for track in ad.get("tracks", []):
        await studio.call("timeline.set_track", **track)

    last = ad["shots"][-1]
    return last["start"] + last["duration"]


def preview_times(ad: dict) -> list[float]:
    """The middle of every shot, and the hero's end."""
    times = [round(s["start"] + 0.5 * s["duration"], 2) for s in ad["shots"]]
    last = ad["shots"][-1]
    return times + [round(last["start"] + last["duration"] - 0.2, 2)]


async def run(names: list[str], preview: bool, width: int, height: int, samples: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with Studio() as studio:
        for name in names:
            ad = ADS[name]
            length = await build(studio, name, ad)
            if preview:
                result = await studio.call("shot.preview", times=preview_times(ad), width=640, height=360,
                                           out_dir=str(OUT / "preview" / name))
                print(f"{name}: {len(result['frames'])} frames in {OUT / 'preview' / name}")
                continue

            raw = OUT / f"{name}_raw.mp4"
            began = time.time()
            result = await studio.call("shot.render", video=str(raw), end=length - 1e-3, fps=30,
                                       width=width, height=height, samples=samples)
            final = finish(raw, OUT / f"{name}.mp4", ad["titles"], fade_in=0.4, fade_out=0.6)
            raw.unlink(missing_ok=True)
            print(f"{name}: {result['frames']} frames in {time.time() - began:.0f}s -> {final}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
    parser.add_argument("--preview", action="store_true", help="a few frames of each as PNGs instead of videos")
    parser.add_argument("--list", action="store_true", help="list the ads and stop")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args()
    if args.list:
        for name, ad in ADS.items():
            print(f"{name:8} {ad['about']}")
        raise SystemExit
    unknown = [a for a in args.ads if a not in ADS]
    if unknown:
        parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")
    asyncio.run(run(args.ads or list(ADS), args.preview, args.width, args.height, args.samples))
