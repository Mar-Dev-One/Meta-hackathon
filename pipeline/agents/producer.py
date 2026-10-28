"""The whole chain: a product photo and a brief in, a finished ad out, as
one run (runs/<time>-ad-<photo>/).

    with Run.create("ad-aurelle") as run:
        video = await make_ad(studio, run, "Luxury perfume ad, dark and moody, 15 seconds.", photo)

The brand analyst reads the photo (brand_profile.json, masks, label), the
director plans the ad (storyboard.json), the Studio builds it, a few frames
are previewed (frames/) and the video rendered and finished (final/).

    python -m pipeline.agents.producer Assets/photos/aurelle_perfume.png "Luxury perfume ad, dark and moody, 15 seconds." --category "perfume bottle"
"""

from pathlib import Path

from pipeline.runs import Run
from pipeline.studio import build, preview, render

from .analyst import analyse
from .director.write import write


async def make_ad(studio, run: Run, brief: str, photo: Path | str, category: str = "product", short: int = 1080,
                  video: bool = True) -> Path | None:
    """The ad for `brief` with the product in `photo`: the video's path
    (None with video=False: only the preview frames)."""
    run.watch(studio)
    run.event("brief", text=brief, photo=Path(photo).name, category=category)
    analysis = analyse(run, photo, category)
    sb = await write(brief, analysis.profile, studio=studio, run=run)
    await build(studio, sb)
    await preview(studio, run, sb)
    if not video:
        return None
    return await render(studio, run, sb, Path(photo).stem, short=short)


if __name__ == "__main__":
    import argparse
    import asyncio
    import json
    import time

    from pipeline.studio import Studio

    parser = argparse.ArgumentParser(description="A product photo and a brief in, a finished ad out (one run).")
    parser.add_argument("photo")
    parser.add_argument("brief")
    parser.add_argument("--category", default="product", help='what the product is, e.g. "perfume bottle"')
    parser.add_argument("--size", type=int, default=1080, help="the video's shorter side in pixels")
    parser.add_argument("--preview", action="store_true", help="only the preview frames, no video")
    args = parser.parse_args()

    async def main() -> None:
        began = time.time()
        async with Studio() as studio:
            with Run.create(f"ad-{Path(args.photo).stem}") as run:
                video = await make_ad(studio, run, args.brief, args.photo, args.category, args.size, not args.preview)
        summary = json.loads((run.root / "run.json").read_text(encoding="utf-8"))
        print(f"{video or run.root / 'frames'}\n{time.time() - began:.0f} s, {summary['model_calls']} model calls "
              f"({summary['cached_calls']} cached), ${summary['cost']:.4f}")

    asyncio.run(main())
