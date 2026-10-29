"""The measured checks on the hand-made ads (pipeline/demos/ads.py), each a
run in runs/<time>-<name>-measure/ with measure.json and a contact sheet.

    python -m pipeline.agents.critic              # every ad
    python -m pipeline.agents.critic noctis kora
"""

import argparse
import asyncio
import json

from pipeline.demos.ads import ADS, storyboard_for
from pipeline.runs import Run
from pipeline.studio import Studio, build

from .measure import measure, sheet

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
args = parser.parse_args()
unknown = [a for a in args.ads if a not in ADS]
if unknown:
    parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")


async def main() -> None:
    async with Studio() as studio:
        for name in args.ads or list(ADS):
            with Run.create(f"{name}-measure") as run:
                run.watch(studio)
                sb = storyboard_for(name)
                run.save_json("storyboard.json", sb)
                await build(studio, sb)
                shots = await measure(studio, sb, run.folder("measure"))
                run.output("measure", run.save_json("measure.json", [s.to_json() for s in shots]))
                sheet(shots).save(run.path("measure", "sheet.png"))
                run.output("sheet", run.path("measure", "sheet.png"))
            print(f"\n{name}  ({run.root})")
            for s in shots:
                print(f"  {s.shot}: {json.dumps(s.summary())}")
                for f in s.flags:
                    print(f"    {f.severity:5} {f.time:>5g}s {f.category}: {f.problem}")


asyncio.run(main())
