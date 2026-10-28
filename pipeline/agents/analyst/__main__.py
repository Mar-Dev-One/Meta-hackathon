"""python -m pipeline.agents.analyst photos... [--category ...] [--video]: one
run each, with its brand profile, contact sheet and (with --video) turntable."""

import argparse
import asyncio
from pathlib import Path

from pipeline.runs import Run
from pipeline.studio import Studio

from .analyse import analyse, contact_sheet, turntable_frames, turntable_video


async def main(photos: list[str], categories: list[str], video: bool) -> None:
    async with Studio() as studio:
        for photo, category in zip(photos, categories):
            with Run.create(f"analyse-{Path(photo).stem}") as run:
                run.watch(studio)
                a = analyse(run, photo, category)
                frames = await turntable_frames(studio, run, a.profile)
                contact_sheet(a, frames).save(run.path("contact_sheet.png"))
                run.output("contact_sheet", run.root / "contact_sheet.png")
                if video:
                    await turntable_video(studio, run, a.profile)
            print(run.root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Product photos in, brand profiles and contact sheets out (one run each).")
    parser.add_argument("photos", nargs="+")
    parser.add_argument("--category", action="append", help="per photo, in order (default: product)")
    parser.add_argument("--video", action="store_true", help="also render the turntable as an mp4")
    args = parser.parse_args()
    asyncio.run(main(args.photos, (args.category or []) + ["product"] * len(args.photos), args.video))
