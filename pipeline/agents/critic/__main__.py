"""The critic on the hand-made ads (pipeline/demos/ads.py), each a run in
runs/<time>-<name>-critic/: measure.json, a contact sheet, and with --judge
a critique per shot in critiques/.

    python -m pipeline.agents.critic                      # every ad, measured
    python -m pipeline.agents.critic noctis kora --judge  # and judged by Muse Spark
    python -m pipeline.agents.critic kora --judge --provider baseten   # by Muse Spark Open
"""

import argparse
import asyncio
import json

from pipeline.demos.ads import ADS, storyboard_for
from pipeline.runs import Run
from pipeline.studio import Studio, build

from .judge import judge
from .measure import measure, sheet

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
parser.add_argument("--judge", action="store_true", help="also score each shot with Muse Spark vision")
parser.add_argument("--provider", default="meta", choices=["meta", "baseten"],
                    help="meta: Muse Spark; baseten: Muse Spark Open")
args = parser.parse_args()
unknown = [a for a in args.ads if a not in ADS]
if unknown:
    parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")


def show(s, critique) -> None:
    print(f"  {s.shot}: {json.dumps(s.summary())}")
    for f in s.flags:
        print(f"    measured {f.severity:5} {f.time:>5g}s {f.category}: {f.problem}")
    if critique:
        scores = " ".join(f"{k}={v}" for k, v in critique.scores.model_dump().items())
        print(f"    {'PASS' if critique.passed else 'FAIL'}  {scores}")
        for i in critique.issues:
            print(f"    judged {i.severity:5} {i.category}: {i.problem}\n{'':17}fix: {i.fix}")


async def main() -> None:
    async with Studio() as studio:
        for name in args.ads or list(ADS):
            with Run.create(f"{name}-critic") as run:
                run.watch(studio)
                sb = storyboard_for(name)
                run.save_json("storyboard.json", sb)
                await build(studio, sb)
                shots = await measure(studio, sb, run.folder("measure"))
                run.output("measure", run.save_json("measure.json", [s.to_json() for s in shots]))
                sheet(shots).save(run.path("measure", "sheet.png"))
                run.output("sheet", run.path("measure", "sheet.png"))
                critiques = [judge(sb, s, provider=args.provider, run=run) if args.judge else None for s in shots]
            print(f"\n{name}  ({run.root})")
            for s, c in zip(shots, critiques):
                show(s, c)


asyncio.run(main())
