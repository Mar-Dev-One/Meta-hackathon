"""Muse Spark against Muse Spark Open as the critic, on the hand-made ads:
the same shots, the same frames and measurements, each judged twice by each
model, to see how far they agree with each other and with themselves.

    python -m pipeline.agents.critic.compare                   # every ad, 2 samples per model
    python -m pipeline.agents.critic.compare kora fizzo --samples 3

One run (runs/<time>-critic-compare/): compare.json (every critique's
verdict), compare.md (the summary), judgments/ (each critique), the frames
each was judged on. Counted
per model:

    self-agreement    the share of shots whose pass/fail is the same in every sample
    score spread      the mean gap between a shot's lowest score in two samples
    cross-agreement   the share of shots both models pass or both fail (first samples)
    score gap         the mean gap between the two models' lowest scores, and per category
    seconds, cost     per critique (Baseten bills Muse Spark Open there: its cost here is 0)
"""

import argparse
import asyncio
import json
import statistics
import time
from itertools import combinations

from pipeline.demos.ads import ADS, storyboard_for
from pipeline.meta import usage
from pipeline.runs import Run
from pipeline.studio import Studio, build

from .judge import CriticError, judge
from .measure import measure

MODELS = {"meta": "Muse Spark", "baseten": "Muse Spark Open"}


def verdicts(studio, sb, shots, provider: str, samples: int, run, ad: str) -> list[dict]:
    """Every shot judged `samples` times by one model: one entry per judgment,
    each critique saved as judgments/<ad>_<shot>_<model>_<sample>.json."""
    out = []
    for shot in shots:
        for sample in range(samples):
            began, calls = time.perf_counter(), len(usage.calls())
            try:
                c = judge(sb, shot, provider=provider, sample=sample, run=run, second_opinion=False)
            except CriticError as e:
                out.append({"shot": shot.shot, "sample": sample, "provider": provider, "error": str(e)})
                continue
            made = usage.calls()[calls:]
            run.save_json(f"judgments/{ad}_{shot.shot}_{provider}_{sample + 1}.json", c)
            out.append({"shot": shot.shot, "sample": sample, "provider": provider, "passed": c.passed,
                        "scores": c.scores.model_dump(), "low": min(c.scores.model_dump().values()),
                        "majors": sum(i.severity == "major" for i in c.issues), "issues": len(c.issues),
                        "seconds": round(time.perf_counter() - began, 1), "cost": sum(x.cost for x in made),
                        "cached": all(x.cached for x in made), "attempts": len(made)})
    return out


def _mean(values) -> float:
    values = list(values)
    return round(statistics.mean(values), 2) if values else float("nan")


def summarise(rows: list[dict], samples: int) -> dict:
    ok = [r for r in rows if "error" not in r]
    by = {(r["ad"], r["shot"], r["provider"], r["sample"]): r for r in ok}
    shots = sorted({(r["ad"], r["shot"]) for r in rows})
    out = {"shots": len(shots), "errors": len(rows) - len(ok), "models": {}}
    for p in MODELS:
        same, spreads = [], []
        for ad, shot in shots:
            got = [by.get((ad, shot, p, s)) for s in range(samples)]
            if all(got):
                same.append(len({g["passed"] for g in got}) == 1)
                spreads += [abs(a["low"] - b["low"]) for a, b in combinations(got, 2)]
        mine = [r for r in ok if r["provider"] == p and not r["cached"]]
        out["models"][MODELS[p]] = {
            "pass_rate": _mean(r["passed"] for r in ok if r["provider"] == p and r["sample"] == 0),
            "self_agreement": _mean(same), "score_spread": _mean(spreads),
            "mean_low": _mean(r["low"] for r in ok if r["provider"] == p and r["sample"] == 0),
            "seconds_per_critique": _mean(r["seconds"] for r in mine),
            "cost_per_critique": round(_mean(r["cost"] for r in mine), 4) if mine else 0.0,
            "retries": sum(r["attempts"] - 1 for r in ok if r["provider"] == p)}
    pairs = [(by.get((ad, shot, "meta", 0)), by.get((ad, shot, "baseten", 0))) for ad, shot in shots]
    pairs = [(a, b) for a, b in pairs if a and b]
    out["cross"] = {"agreement": _mean(a["passed"] == b["passed"] for a, b in pairs),
                    "both_pass": sum(a["passed"] and b["passed"] for a, b in pairs),
                    "both_fail": sum(not a["passed"] and not b["passed"] for a, b in pairs),
                    "only_spark_passes": sum(a["passed"] and not b["passed"] for a, b in pairs),
                    "only_open_passes": sum(b["passed"] and not a["passed"] for a, b in pairs),
                    "low_gap": _mean(abs(a["low"] - b["low"]) for a, b in pairs),
                    "open_minus_spark": {k: _mean(b["scores"][k] - a["scores"][k] for a, b in pairs)
                                         for k in pairs[0][0]["scores"]} if pairs else {}}
    return out


def report(summary: dict, rows: list[dict], samples: int) -> str:
    m, x = summary["models"], summary["cross"]
    lines = ["# Critic: Muse Spark vs Muse Spark Open", "",
             f"{summary['shots']} shots from the hand-made ads, the same frames and measurements, judged "
             f"{samples} times by each model. {summary['errors']} judgments failed.", "",
             "| | " + " | ".join(m) + " |", "|---|" + "---|" * len(m)]
    for key, label in (("pass_rate", "share of shots passed"), ("mean_low", "mean lowest score"),
                       ("self_agreement", "same pass/fail in every sample"), ("score_spread", "lowest score's spread between samples"),
                       ("seconds_per_critique", "seconds per critique"), ("cost_per_critique", "cost per critique ($)"),
                       ("retries", "answers sent back")):
        lines.append(f"| {label} | " + " | ".join(str(v[key]) for v in m.values()) + " |")
    lines += ["", f"The two agree on pass/fail for {x['agreement']:.0%} of shots ({x['both_pass']} both pass, "
                  f"{x['both_fail']} both fail, {x['only_spark_passes']} only Muse Spark passes, "
                  f"{x['only_open_passes']} only Muse Spark Open passes); their lowest scores differ by "
                  f"{x['low_gap']} on average.", "",
              "Muse Spark Open's scores minus Muse Spark's, per category: " +
              ", ".join(f"{k} {v:+g}" for k, v in x["open_minus_spark"].items()) + ".", "",
              "Muse Spark Open's cost is billed by Baseten, not counted here.", "", "## Per shot", "",
              "| ad | shot | " + " | ".join(f"{name} s{s}" for name in MODELS.values() for s in range(samples)) + " |",
              "|---|---|" + "---|" * (len(MODELS) * samples)]
    by = {(r["ad"], r["shot"], r["provider"], r["sample"]): r for r in rows}
    for ad, shot in sorted({(r["ad"], r["shot"]) for r in rows}):
        cells = []
        for p in MODELS:
            for s in range(samples):
                r = by.get((ad, shot, p, s))
                cells.append("error" if not r or "error" in r else f"{'pass' if r['passed'] else 'fail'} {r['low']}")
        lines.append(f"| {ad} | {shot} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


async def main(names: list[str], samples: int) -> None:
    rows = []
    async with Studio() as studio:
        with Run.create("critic-compare") as run:
            run.watch(studio)
            for name in names:
                sb = storyboard_for(name)
                await build(studio, sb)
                shots = await measure(studio, sb, run.folder("ads", name))
                for provider in MODELS:
                    for r in verdicts(studio, sb, shots, provider, samples, run, name):
                        rows.append({"ad": name, **r})
                        print(name, json.dumps({k: v for k, v in r.items() if k not in ("scores",)}))
            summary = summarise(rows, samples)
            run.save_json("compare.json", {"summary": summary, "rows": rows})
            text = report(summary, rows, samples)
            run.path("compare.md").write_text(text, encoding="utf-8")
            run.output("report", run.path("compare.md"))
    print("\n" + text + f"\n{run.root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ads", nargs="*", help=f"which ads (default all): {', '.join(ADS)}")
    parser.add_argument("--samples", type=int, default=2, help="judgments per shot per model (default 2)")
    args = parser.parse_args()
    unknown = [a for a in args.ads if a not in ADS]
    if unknown:
        parser.error(f"unknown ad(s) {unknown}; there are {list(ADS)}")
    asyncio.run(main(args.ads or list(ADS), args.samples))
