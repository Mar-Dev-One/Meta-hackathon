"""Numbers for the README and the demo, from the runs' own logs: how often an
ad gets made, its time and cost, how the director's drafts go (problems the
checks find, how many the next draft fixes), where the time goes, and how
the 3D-model steps decide.

    python scripts/evaluate.py                    # every ad run
    python scripts/evaluate.py --since 20261101   # runs started that day or later (their ids sort by time)
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.runs import RUNS, events  # noqa: E402

PRIVATE = ("iphone",)   # real-brand tests: never in the numbers we show


def ad_runs(since: str) -> list[Path]:
    return sorted(r for r in RUNS.iterdir() if r.is_dir() and "-ad-" in r.name and r.name >= since
                  and not any(word in r.name.lower() for word in PRIVATE) and (r / "log.jsonl").exists())


def median(values: list[float]) -> str:
    return f"{statistics.median(values):.0f}" if values else "-"


def main() -> None:
    parser = argparse.ArgumentParser(description="Numbers from the runs' logs.")
    parser.add_argument("--since", default="", help="only runs whose id is at or after this (e.g. 20261101)")
    args = parser.parse_args()
    runs = ad_runs(args.since)
    status = Counter()
    seconds, costs, calls, cached = [], [], [], []
    drafts_per_ad, first_clean, problems_found, fixed, kept_warned = [], 0, 0, 0, 0
    steps: dict[str, list[float]] = {}
    model_steps = Counter()
    for root in runs:
        summary = json.loads((root / "run.json").read_text(encoding="utf-8")) if (root / "run.json").exists() else {}
        status[summary.get("status", "stopped")] += 1
        if summary.get("status") != "done":
            continue
        seconds.append(summary["seconds"])
        costs.append(summary["cost"])
        calls.append(summary["model_calls"])
        cached.append(summary["cached_calls"])
        log = events(root)
        drafts = [e for e in log if e["kind"] == "draft"]
        if drafts:
            drafts_per_ad.append(len(drafts))
            first_clean += not drafts[0].get("problems")
            for a, b in zip(drafts, drafts[1:]):   # a problem of one draft gone from the next: fixed
                before = {p.split(":")[0] for p in a.get("problems", [])}
                after = {p.split(":")[0] for p in b.get("problems", [])}
                problems_found += len(before)
                fixed += len(before - after)
            kept_warned += any(e["kind"] == "draft_warnings" for e in log)
        ticks = [e for e in log if e["kind"] == "progress"]
        span: dict[str, list[float]] = {}
        for e in ticks:
            span.setdefault(e["step"], [e["t"], e["t"]])[1] = e["t"]
        for step, (a, b) in span.items():
            steps.setdefault(step.split(" ")[0] if step.startswith("Rendering") else step, []).append(b - a)
        for e in log:
            if e["kind"] == "model_audition":
                model_steps["model picked by its render" if not e.get("error") else "model picked by thumbnail (renders failed)"] += 1
            elif e["kind"] == "staged":
                model_steps["stood by Spark" if e.get("by") == "spark" else "stood by proportions (Spark failed)"] += 1
            elif e["kind"] == "recoloured":
                model_steps["repainted in the photo's colours" if e.get("by") else
                            "kept its own colours" + (" (failed)" if e.get("error") else " (Spark's choice)")] += 1
            elif e["kind"] == "scouted":
                model_steps["round: traced from the photo" if e.get("round") else "not round: a 3D model found"] += 1

    done = status["done"]
    print(f"# Evaluation ({len(runs)} ad runs{', since ' + args.since if args.since else ''}; real-brand tests left out)\n")
    print("| | |\n|---|---|")
    print(f"| made | {done} of {len(runs)} ({100 * done / max(len(runs), 1):.0f}%): "
          + ", ".join(f"{n} {s}" for s, n in status.most_common() if s != "done") + " |")
    if done:
        print(f"| time per ad | median {median(seconds)} s ({min(seconds):.0f}-{max(seconds):.0f}) |")
        print(f"| Meta models per ad | median ${statistics.median(costs):.3f}, {statistics.median(calls):.0f} calls "
              f"({sum(cached)} of {sum(calls)} answered from the cache) |")
    if drafts_per_ad:
        print(f"| director's drafts per ad | mean {statistics.mean(drafts_per_ad):.1f}; first draft clean in "
              f"{first_clean} of {len(drafts_per_ad)} |")
        print(f"| problems the checks found in a draft | {problems_found}; the next draft fixed {fixed} "
              f"({100 * fixed / max(problems_found, 1):.0f}%) |")
        print(f"| kept with taste warnings only | {kept_warned} of {len(drafts_per_ad)} |")
    print("\n## Where the time goes (median seconds per ad)\n\n| step | s |\n|---|---|")
    for step, values in steps.items():
        print(f"| {step} | {median(values)} |")
    print("\n## The product's 3D model\n\n| | runs |\n|---|---|")
    for what, n in model_steps.most_common():
        print(f"| {what} | {n} |")


if __name__ == "__main__":
    main()
