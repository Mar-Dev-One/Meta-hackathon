"""The first ad, written by hand: no AI, just the Studio's commands in order.
A dark, moody 13-second spot for a fictional perfume, "Noctis -- Noir
Absolu": the shot list a director agent will later write for itself.

    python -m pipeline.demos.first_ad              # the video: pipeline/demos/out/first_ad.mp4
    python -m pipeline.demos.first_ad --preview    # a few frames as PNGs, to check the look first

Until the Studio builds product meshes (docs/ROADMAP.md, Phase 1.6) the
bottle is two boxes: a deep plum glass body and a gold cap.
"""

import argparse
import asyncio
import math
import time
from pathlib import Path

from pipeline.encode import Title, finish
from pipeline.studio import Studio

OUT = Path(__file__).resolve().parent / "out"


async def spot(studio: Studio, name: str, position, target, color, intensity: float, cone: float = 30.0):
    """A spot light at `position` aimed at `target`."""
    d = [t - p for p, t in zip(position, target)]
    length = math.sqrt(sum(x * x for x in d))
    await studio.call("entity.create", name=name, components={
        "Transform": {"position": list(position)},
        "Light": {"type": "spot", "color": list(color), "intensity": intensity, "direction": [x / length for x in d],
                  "range": 6.0, "inner_cone_degrees": cone * 0.6, "outer_cone_degrees": cone, "cast_shadows": True},
    })


async def box(studio: Studio, name: str, center, size, color, metallic: float, roughness: float):
    """A built-in cube (1 unit across) scaled to `size`, centred on `center`."""
    await studio.call("entity.create", name=name, components={
        "Transform": {"position": list(center), "scale": list(size)},
        "MeshRenderer": {"model": "builtin:cube", "material.base_color": list(color),
                         "material.metallic": metallic, "material.roughness": roughness},
    })


async def build_scene(studio: Studio) -> None:
    await studio.call("studio.reset")
    # The HDRI only lights and reflects; the background stays near black.
    await studio.call("environment.set", hdri="hdri/citrus_orchard_road_puresky_4k.hdr", use_ibl=True,
                      show_skybox=False, ambient_strength=0.05, exposure=1.0, bloom=0.08, tonemap="agx", ssao=True)
    await studio.call("render.set", antialiasing="taa", clear_color=[0.004, 0.004, 0.006])

    await studio.call("entity.create", name="floor", components={
        "Transform": {"scale": [12, 1, 12]},
        "MeshRenderer": {"model": "builtin:plane", "material.base_color": [0.012, 0.012, 0.014], "material.roughness": 0.65},
    })
    await box(studio, "pedestal", (0, 0.15, 0), (0.5, 0.3, 0.5), (0.015, 0.015, 0.017), 0.0, 0.75)
    await box(studio, "bottle", (0, 0.41, 0), (0.16, 0.22, 0.07), (0.12, 0.03, 0.08), 0.0, 0.06)
    await box(studio, "cap", (0, 0.55, 0), (0.075, 0.06, 0.075), (1.0, 0.77, 0.38), 1.0, 0.22)

    product = (0, 0.45, 0)
    await spot(studio, "key", (-0.9, 1.2, 1.3), product, (1.0, 0.92, 0.82), 2.5, cone=22)
    await spot(studio, "rim_warm", (-0.7, 0.55, -1.1), product, (1.0, 0.62, 0.30), 30.0, cone=14)
    await spot(studio, "rim_cool", (0.75, 0.55, -1.0), product, (0.45, 0.60, 1.0), 22.0, cone=14)


async def build_shots(studio: Studio) -> float:
    """The shot list; returns the ad's length in seconds."""
    shots = [
        # Out of the dark: the aim comes down onto the bottle as the rims come up.
        dict(move="reveal", start=0, duration=3, fill=0.45, azimuth=-15, elevation=4, **{"from": "above"}),
        # Around it, low: the rim lights slide across the glass.
        dict(move="orbit", start=3, duration=4, azimuth=-60, to_azimuth=10, elevation=3, fill=0.55),
        # In close on the cap.
        dict(move="dolly", start=7, duration=3, azimuth=20, elevation=8, from_fill=0.5, to_fill=0.8),
        # The hero: still, room below for the name.
        dict(move="static", start=10, duration=3, azimuth=0, elevation=2, fill=0.42),
    ]
    for shot in shots:
        await studio.call("camera.move", subject="bottle", **shot)

    # The rims rise from darkness during the first shot.
    for name, full in (("rim_warm", 30.0), ("rim_cool", 22.0)):
        await studio.call("timeline.set_track", entity=name, component="Light", field="intensity",
                          keys=[{"t": 0, "value": 0.0, "ease": "in"}, {"t": 2.5, "value": full}])
    return shots[-1]["start"] + shots[-1]["duration"]


TITLES = [
    Title("NOCTIS", start=10.6, end=13.0, size=0.075, y=0.83, tracking=3),
    Title("NOIR ABSOLU", start=11.0, end=13.0, size=0.028, y=0.905, color="#c9a45c", tracking=2),
]


async def main(args) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with Studio() as studio:
        await build_scene(studio)
        length = await build_shots(studio)

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
