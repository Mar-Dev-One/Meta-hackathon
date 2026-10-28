"""A built storyboard out of the Studio, into a run: a few preview frames,
or the finished video. The hand-made ads and the director both render
through this.

    length = await build(studio, sb)
    frames = await preview(studio, run, sb)                # frames/: the middle of each shot, and the end
    video = await render(studio, run, sb, "aurelle")       # final/aurelle.mp4, faded in and out

Sizes follow the storyboard's frame: `short` is its shorter side, so 1080
gives 1920x1080, 1080x1920 or 1080x1080.
"""

import time
from pathlib import Path

from pipeline.encode import finish
from pipeline.schemas import Storyboard

ASPECT_SIZES = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1)}


def frame_size(aspect: str, short: int) -> tuple[int, int]:
    """Width and height for a frame of `aspect` whose shorter side is `short`
    (both even, as H.264 needs)."""
    w, h = ASPECT_SIZES[aspect]
    scale = short / min(w, h)
    return round(w * scale / 2) * 2, round(h * scale / 2) * 2


def preview_times(sb: Storyboard) -> list[float]:
    """The middle of every shot, and just before the end."""
    return [round(start + 0.5 * shot.duration, 2) for start, shot in zip(sb.shot_starts(), sb.shots)] + \
           [round(sb.duration - 0.2, 2)]


async def preview(studio, run, sb: Storyboard, short: int = 360, samples: int = 8) -> list[Path]:
    """The built storyboard's frames at preview_times, in the run's frames/."""
    width, height = frame_size(sb.aspect, short)
    result = await studio.call("shot.preview", times=preview_times(sb), width=width, height=height, samples=samples,
                               out_dir=str(run.folder("frames")))
    frames = [Path(f["path"]) for f in result["frames"]]
    run.event("preview", frames=[str(f.relative_to(run.root)) for f in frames])
    run.output("frames", run.root / "frames")
    return frames


async def render(studio, run, sb: Storyboard, name: str, short: int = 1080, samples: int = 16,
                 fade_in: float = 0.4, fade_out: float = 0.6) -> Path:
    """The built storyboard as final/<name>.mp4 in the run, faded from and to black."""
    width, height = frame_size(sb.aspect, short)
    raw = run.path("final", "raw.mp4")
    frames = round(sb.duration * sb.fps)
    run.event("render", frames=frames, width=width, height=height, samples=samples)
    began = time.time()
    result = await studio.call("shot.render", video=str(raw), end=sb.duration - 1e-3, fps=sb.fps, width=width,
                               height=height, samples=samples)
    run.event("rendered", frames=result["frames"], seconds=round(time.time() - began, 1))
    video = finish(raw, run.path("final", f"{name}.mp4"), fade_in=fade_in, fade_out=fade_out)
    raw.unlink(missing_ok=True)
    run.output("video", video)
    return video
