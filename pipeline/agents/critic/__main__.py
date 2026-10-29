"""The critic on the hand-made ads (pipeline/demos/ads.py), each a run in
runs/<time>-<name>-critic/: measure.json, a contact sheet, and with --judge
a critique per shot in critiques/; with --refine, the whole loop (rounds/).

    python -m pipeline.agents.critic                      # every ad, measured
    python -m pipeline.agents.critic noctis kora --judge  # and judged by Muse Spark
    python -m pipeline.agents.critic kora --judge --provider baseten   # by Muse Spark Open
    python -m pipeline.agents.critic fizzo --refine --broken           # broken on purpose, fixed by the loop
    python -m pipeline.agents.critic --resume runs/<folder>            # a refine run that stopped, carried on
    python -m pipeline.agents.critic --refine --storyboard sb.json --broken-cut   # any storyboard; a cut broken
"""

import argparse
import asyncio
import json

from pipeline.demos.ads import ADS, storyboard_for
from pipeline.runs import Run
from pipeline.schemas import Storyboard
from pipeline.studio import Studio, build

from .cuts import measure_cuts
from .judge import judge
from .loop import refine, summary
from .measure import measure, sheet

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
parser.add_argument("--judge", action="store_true", help="also score each shot with Muse Spark vision")
parser.add_argument("--cuts", action="store_true", help="also measure every cut: the last frame of a shot against "
                                                        "the first of the next")
parser.add_argument("--refine", action="store_true", help="the critic loop: judge, revise, rebuild, up to 3 times")
parser.add_argument("--broken", action="store_true", help="break the ad first: a shot slides the product out of "
                                                          "frame and the light is nearly off")
parser.add_argument("--broken-cut", action="store_true", help="break the cut into the third shot: seen from "
                                                              "behind, and the lights change colour at the cut")
parser.add_argument("--storyboard", metavar="FILE", help="start from this storyboard (JSON) instead of an ad")
parser.add_argument("--resume", metavar="RUN", help="carry on a refine run that stopped, from its last finished round")
parser.add_argument("--provider", default="meta", choices=["meta", "baseten"],
                    help="the critic's model -- meta: Muse Spark; baseten: Muse Spark Open")
args = parser.parse_args()
unknown = [a for a in args.ads if a not in ADS]
if unknown:
    parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")


def broken(sb: Storyboard) -> Storyboard:
    """The ad with two faults a viewer would see: the second-to-last shot
    slides past the product until it leaves the frame, and the light is
    down to a fifth."""
    data = sb.model_dump(by_alias=True, exclude_none=True)
    data["look"]["lighting"]["intensity"] = 0.2
    shot = data["shots"][-2]
    shot["camera"] = {"move": "truck", "travel": 0.5, "fill": shot["camera"].get("fill", 0.6), "elevation": 5}
    return Storyboard.model_validate(data)


def broken_cut(sb: Storyboard) -> Storyboard:
    """The ad with a jarring cut into its third shot: the camera swings to
    the back of the product, and every light changes colour at the cut (a
    step, so the shots before keep theirs)."""
    data = sb.model_dump(by_alias=True, exclude_none=True)
    camera = data["shots"][2]["camera"]
    camera["azimuth"] = 180
    if "to_azimuth" in camera:
        camera["to_azimuth"] = 200
    cut = sb.shot_starts()[2]
    for name, colour in LIGHT_SWAP.items():
        data["tracks"].append({"entity": name, "component": "Light", "field": "color",
                               "keys": [{"t": 0, "value": colour[0], "ease": "step"}, {"t": cut, "value": colour[1]}]})
    return Storyboard.model_validate(data)


# neon_dual's rims (pipeline/demos/ads.py's fizzo): pink and cyan, then green and orange.
LIGHT_SWAP = {"light_rim_left": ([1, 0.15, 0.75], [0.2, 1, 0.2]), "light_rim_right": ([0.1, 0.85, 1], [1, 0.5, 0.05])}


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
        if args.resume:
            with Run.reopen(args.resume) as run:
                run.watch(studio)
                _, rounds = await refine(studio, None, None, run, provider=args.provider, resume=True)
            print(f"\n{run.root}\n{summary(rounds)}")
            return
        if args.storyboard:
            sb = Storyboard.model_validate_json(open(args.storyboard, encoding="utf-8").read())
            sb = broken_cut(sb) if args.broken_cut else sb
            with Run.create(f"storyboard{'-broken-cut' if args.broken_cut else ''}-refine") as run:
                run.watch(studio)
                run.save_json("storyboard.json", sb)
                _, rounds = await refine(studio, sb, None, run, provider=args.provider)
            print(f"\n{run.root}\n{summary(rounds)}")
            return
        for name in args.ads or list(ADS):
            with Run.create(f"{name}{'-broken' if args.broken else ''}-{'refine' if args.refine else 'critic'}") as run:
                run.watch(studio)
                sb = storyboard_for(name)
                if args.broken:
                    sb = broken(sb)
                if args.broken_cut:
                    sb = broken_cut(sb)
                run.save_json("storyboard.json", sb)
                if args.refine:
                    _, rounds = await refine(studio, sb, None, run, provider=args.provider)
                    print(f"\n{name}  ({run.root})\n{summary(rounds)}")
                    continue
                await build(studio, sb)
                shots = await measure(studio, sb, run.folder("measure"))
                run.output("measure", run.save_json("measure.json", [s.to_json() for s in shots]))
                sheet(shots).save(run.path("measure", "sheet.png"))
                run.output("sheet", run.path("measure", "sheet.png"))
                critiques = [judge(sb, s, provider=args.provider, run=run) if args.judge else None for s in shots]
                cuts = await measure_cuts(studio, sb, run.folder("cuts")) if args.cuts else []
                if cuts:
                    run.output("cuts", run.save_json("cuts.json", [c.to_json() for c in cuts]))
            print(f"\n{name}  ({run.root})")
            for s, c in zip(shots, critiques):
                show(s, c)
            for c in cuts:
                print(f"  cut {c.before}->{c.after} at {c.time:g}s: view {c.view[0]:.0f}->{c.view[1]:.0f} "
                      f"({c.view_jump:+.0f}), lights x{c.set_light} colour {c.set_colour:.1f}, frame light "
                      f"{c.light_jump:+.1f} colour {c.colour_jump:.1f}, product "
                      f"{c.product_light:+.1f}, centre {c.centre_jump:.2f}, size x{c.size_ratio}")
                for f in c.flags:
                    print(f"    measured {f.severity:5} {f.problem}")


asyncio.run(main())
