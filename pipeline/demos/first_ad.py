"""The first ad, written by hand: no AI, just the Studio's commands in order.
A dark, moody 13-second spot for a fictional perfume, "Noctis -- Noir
Absolu": the shot list a director agent will later write for itself.

    python -m pipeline.demos.first_ad              # the video: pipeline/demos/out/first_ad.mp4
    python -m pipeline.demos.first_ad --preview    # a few frames as PNGs, to check the look first

The bottle is the Studio's perfume template with a label drawn here with
Pillow; the brand analyst will later make both from a product photo.
"""

import argparse
import asyncio
import time
from pathlib import Path

from pipeline.encode import Title, finish
from pipeline.studio import Studio

OUT = Path(__file__).resolve().parent / "out"


def make_label(path: Path) -> Path:
    """The label artwork: cream paper, a thin gold border, the name in a serif."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1200, 800
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))   # transparent outside the rounded corners
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=60, fill=(236, 226, 206, 255))
    d.rounded_rectangle([30, 30, w - 31, h - 31], radius=40, outline=(160, 122, 62, 255), width=6)
    for text, size, y, color in (("N O C T I S", 170, 250, (30, 22, 18)), ("NOIR ABSOLU", 64, 560, (120, 90, 50))):
        font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", size)
        d.text(((w - d.textlength(text, font=font)) / 2, y), text, font=font, fill=color + (255,))
    img.save(path)
    return path


async def build_scene(studio: Studio) -> dict:
    """The set; returns the preset's lights by entity name, with their intensities."""
    await studio.call("studio.reset")
    # The HDRI only lights and reflects; the background stays near black.
    await studio.call("environment.set", hdri="hdri/citrus_orchard_road_puresky_4k.hdr", use_ibl=True,
                      show_skybox=False, ambient_strength=0.06, exposure=1.0, bloom=0.08, tonemap="agx", ssao=True)
    await studio.call("render.set", antialiasing="taa", clear_color=[0.004, 0.004, 0.006])

    await studio.call("backdrop.create", kind="cyclorama", color="#0a0a0c", roughness=0.6)
    await studio.call("backdrop.create", kind="pedestal", width=0.32, height=0.22, color="#0e0e10", roughness=0.85)
    await studio.call("product.create", name="product", template="perfume", position=[0, 0.22, 0],
                      parts={"body": {"color": "#4a1030", "opacity": 0.92, "roughness": 0.04},
                             "cap": {"color": "#d4af6a", "roughness": 0.18}},
                      label={"image": str(make_label(OUT / "noctis_label.png")), "arc": 110})
    lights = await studio.call("lighting.preset", name="rim_dark", subject="product")
    return {light["entity"]: light["intensity"] for light in lights["lights"]}


async def build_shots(studio: Studio, lights: dict) -> float:
    """The shot list; returns the ad's length in seconds."""
    shots = [
        # Out of the dark: the aim comes down onto the bottle as the rims come up.
        dict(move="reveal", start=0, duration=3, fill=0.5, azimuth=-15, elevation=4, **{"from": "above"}),
        # Around it, low: the rim lights slide across the glass.
        dict(move="orbit", start=3, duration=4, azimuth=-60, to_azimuth=10, elevation=3, fill=0.6),
        # In close on the label and cap.
        dict(move="dolly", start=7, duration=3, azimuth=12, elevation=8, from_fill=0.55, to_fill=0.95),
        # The hero: still, room below for the name.
        dict(move="static", start=10, duration=3, azimuth=0, elevation=2, fill=0.45),
    ]
    for shot in shots:
        await studio.call("camera.move", subject="product", **shot)

    # The rims rise from darkness during the first shot.
    for name in ("light_rim_left", "light_rim_right"):
        await studio.call("timeline.set_track", entity=name, component="Light", field="intensity",
                          keys=[{"t": 0, "value": 0.0, "ease": "in"}, {"t": 2.5, "value": lights[name]}])
    return shots[-1]["start"] + shots[-1]["duration"]


TITLES = [
    Title("NOCTIS", start=10.6, end=13.0, size=0.075, y=0.83, tracking=3),
    Title("NOIR ABSOLU", start=11.0, end=13.0, size=0.028, y=0.905, color="#c9a45c", tracking=2),
]


async def main(args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with Studio() as studio:
        lights = await build_scene(studio)
        length = await build_shots(studio, lights)

        if args.preview:
            times = [0.4, 1.5, 2.9, 3.5, 5.0, 6.9, 7.2, 9.8, 11.5]
            result = await studio.call("shot.preview", times=times, width=960, height=540, out_dir=str(OUT / "preview"))
            for frame in result["frames"]:
                print(frame["path"])
            return

        raw = OUT / "first_ad_raw.mp4"
        began = time.time()
        result = await studio.call("shot.render", video=str(raw), end=length - 1e-3, fps=30,
                                   width=args.width, height=args.height, samples=args.samples)
        print(f"rendered {result['frames']} frames in {time.time() - began:.0f}s")

    final = finish(raw, OUT / "first_ad.mp4", TITLES, fade_in=0.6, fade_out=0.8)
    print(final)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true", help="a few frames as PNGs instead of the video")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=16)
    asyncio.run(main(parser.parse_args()))
