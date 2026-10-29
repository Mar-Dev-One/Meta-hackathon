"""The critic loop: build, measure, judge every shot and the whole ad; if
any fails, the director revises the storyboard from the critiques, and
round again.

    best, rounds = await refine(studio, sb, profile, run)       # at most 3 revisions
    rounds[-1].passed, [r.score for r in rounds]

The set (light, backdrop, pedestal) is shared by every shot, so a fix for
one shot can change the others: each round rebuilds the whole ad and judges
every shot. An unchanged shot renders the same frames in the same Studio
session, so its critique comes from the cache (a new session can differ by a
level in a few pixels, and then it's judged again). The cuts are measured
and the whole ad judged too (whole.py), every round: a shot can be fine on
its own and cut badly from the one before, which matters more than a shot's
small flaw, so it doesn't wait for every shot to pass. A round passes when
every shot and the ad do. The director gets the ad's issues and the failing
shots', the worst first, with the shots that passed named so it leaves them
be, and what earlier rounds changed and how the scores moved, so it doesn't
undo a fix.

Every round is kept in the run: rounds/<i>/ holds its storyboard, frames,
masks and contact sheet (and cuts/, filmstrip.png, cuts.png for the whole
ad); critiques/<shot>.<i>.json and ad.<i>.json its critiques; the log a
"round" event with every shot's scores and the ad's. If no round passes, the
best one is kept: the most shots passing (the whole ad counting as one more),
then the highest lowest score.

A run that stopped (the network, a crash) carries on from its last finished
round: refine(studio, None, profile, Run.reopen(folder), resume=True). The
rounds after it are new: their shots may be judged again (above), so they
can turn out differently.
"""

from dataclasses import dataclass

from pipeline.agents.director.revise import revise
from pipeline.agents.director.write import DirectorError
from pipeline.runs import Run, events
from pipeline.schemas import AdCritique, BrandProfile, Critique, Storyboard
from pipeline.studio import build

from .cuts import measure_cuts
from .judge import judge
from .measure import measure, sheet
from .whole import judge_ad

ROUNDS = 3        # revisions at most (so up to 4 looks)


@dataclass
class Round:
    index: int
    storyboard: Storyboard
    critiques: list[Critique]
    changes: list[str]           # what the revision that made it changed ([] for the first)
    ad: AdCritique | None = None  # the whole ad's (None only in runs from before it existed)

    @property
    def shots_passed(self) -> bool:
        return all(c.passed for c in self.critiques)

    @property
    def passed(self) -> bool:
        return self.shots_passed and self.ad is not None and self.ad.passed

    @property
    def score(self) -> tuple[int, int, float]:
        """For choosing the best round: shots passing (and the whole ad, as
        one more), the lowest score, the mean of the shots' lowest."""
        lows = [_low(c) for c in self.critiques] + ([_low(self.ad)] if self.ad else [])
        passing = sum(c.passed for c in self.critiques) + bool(self.ad and self.ad.passed)
        return passing, min(lows), round(sum(lows) / len(lows), 2)


def fix_text(r: Round, history: list[Round]) -> str:
    """What the director is asked to change: the failing shots' issues (major
    first), the shots that passed, and the earlier rounds."""
    lines = [f"The critic looked at every shot of the ad (round {r.index}). Fix what failed; each fix it suggests "
             f"is a starting point in storyboard terms, use your judgment on the values.", ""]
    if r.ad and not r.ad.passed:
        scores = ", ".join(f"{k} {v}" for k, v in r.ad.scores.model_dump().items())
        lines.append(f"## The whole ad failed ({scores})")
        for i in sorted(r.ad.issues, key=lambda i: i.severity != "major"):
            lines.append(f"- {i.severity} {i.category} ({i.where}): {i.problem}\n  suggested fix: {i.fix}")
        lines.append("")
    for c in r.critiques:
        if c.passed:
            continue
        scores = ", ".join(f"{k} {v}" for k, v in c.scores.model_dump().items())
        lines.append(f"## {c.shot} failed ({scores})")
        for i in sorted(c.issues, key=lambda i: i.severity != "major"):
            at = f" at {i.time:g} s" if i.time is not None else ""
            lines.append(f"- {i.severity} {i.category}{at}: {i.problem}\n  suggested fix: {i.fix}")
        lines.append("")
    passed = [c.shot for c in r.critiques if c.passed]
    if passed:
        lines.append(f"These passed: {', '.join(passed)}. Leave them as they are, unless a change to the shared "
                     f"look (light, set) is needed; then say so.")
    if history:
        lines += ["", "## Earlier rounds (don't undo what they fixed)"]
        for before, after in zip(history, history[1:] + [r]):
            moved = "; ".join(f"{a.shot} {_low(b)} -> {_low(a)}" for b, a in zip(before.critiques, after.critiques))
            lines.append(f"- round {after.index} changed: {', '.join(after.changes) or 'nothing'}. Lowest scores: {moved}")
    return "\n".join(lines)


def _low(c: Critique | AdCritique) -> int:
    return min(c.scores.model_dump().values())


async def look(studio, run: Run, sb: Storyboard, index: int, changes: list[str], profile: BrandProfile | None,
               provider: str) -> Round:
    """One round: the storyboard built, measured and judged."""
    run.save_json(f"rounds/{index}/storyboard.json", sb)
    await build(studio, sb)
    shots = await measure(studio, sb, run.folder("rounds", str(index)))
    run.save_json(f"rounds/{index}/measure.json", [s.to_json() for s in shots])
    sheet(shots).save(run.path("rounds", str(index), "sheet.png"))
    critiques = [judge(sb, s, profile, iteration=index, provider=provider, run=run) for s in shots]
    r = Round(index, sb, critiques, changes)
    cuts = await measure_cuts(studio, sb, run.folder("rounds", str(index), "cuts"))
    run.save_json(f"rounds/{index}/cuts.json", [c.to_json() for c in cuts])
    r.ad = judge_ad(sb, shots, cuts, profile, out_dir=run.folder("rounds", str(index)), iteration=index,
                    provider=provider, run=run)
    run.event("round", index=index, passed=r.passed, score=r.score, changes=changes,
              shots={c.shot: {"passed": c.passed, "scores": c.scores.model_dump(),
                              "majors": sum(i.severity == "major" for i in c.issues)} for c in critiques},
              ad={"passed": r.ad.passed, "scores": r.ad.scores.model_dump(),
                  "majors": sum(i.severity == "major" for i in r.ad.issues)} if r.ad else None)
    return r


def finished_rounds(run: Run) -> list[Round]:
    """The rounds a run already finished (each logged as a "round" event once
    every shot was judged), read back from its folder, in order."""
    found = {}
    for e in events(run.root):
        if e["kind"] == "round":
            i = e["index"]
            sb = Storyboard.model_validate_json(run.path("rounds", str(i), "storyboard.json").read_text(encoding="utf-8"))
            critiques = [Critique.model_validate_json(run.path("critiques", f"{s.id}.{i}.json").read_text(encoding="utf-8"))
                         for s in sb.shots]
            ad = run.path("critiques", f"ad.{i}.json")
            found[i] = Round(i, sb, critiques, e["changes"],
                             AdCritique.model_validate_json(ad.read_text(encoding="utf-8")) if ad.exists() else None)
    return [found[i] for i in sorted(found)]


async def refine(studio, sb: Storyboard | None, profile: BrandProfile | None, run: Run, rounds: int = ROUNDS,
                 provider: str = "meta", resume: bool = False) -> tuple[Storyboard, list[Round]]:
    """The storyboard after at most `rounds` revisions: the first that
    passes, or the best looked at. The Studio is left built with it. With
    `resume`, the run's finished rounds are read back and it carries on from
    the last (`sb` may then be None)."""
    history = finished_rounds(run) if resume else []
    built = None   # the round the Studio holds now
    if history:
        run.event("resumed_rounds", rounds=[r.index for r in history])
    else:
        if sb is None:
            raise ValueError(f"nothing to resume in {run.root}, and no storyboard to start from")
        history, built = [await look(studio, run, sb, 0, [], profile, provider)], 0
    while not history[-1].passed and len(history) <= rounds:
        last = history[-1]
        try:
            revised, changes = await revise(last.storyboard, fix_text(last, history[:-1]), profile, studio=studio,
                                            run=run)
        except DirectorError as e:
            run.event("revision_failed", round=last.index + 1, error=str(e))
            break
        if not changes:
            run.event("revision_failed", round=last.index + 1, error="the revision changed nothing")
            break
        history.append(await look(studio, run, revised, last.index + 1, changes, profile, provider))
        built = last.index + 1

    best = next((r for r in history if r.passed), None) or max(history, key=lambda r: r.score)
    if best.index != built:
        await build(studio, best.storyboard)
    run.output("storyboard", run.save_json("storyboard.json", best.storyboard))
    run.output("sheet", run.path("rounds", str(best.index), "sheet.png"))
    run.event("refined", best=best.index, passed=best.passed, rounds=len(history) - 1,
              scores=[r.score for r in history])
    return best.storyboard, history


def summary(rounds: list[Round]) -> str:
    """The rounds as lines: each shot's lowest score, what changed."""
    out = []
    for r in rounds:
        shots = "  ".join(f"{c.shot} {'ok' if c.passed else 'FAIL'} {_low(c)}" for c in r.critiques)
        ad = f"   ad {'ok' if r.ad.passed else 'FAIL'} {_low(r.ad)}" if r.ad else ""
        out.append(f"round {r.index}: {shots}{ad}   score {r.score}")
        for change in r.changes:
            out.append(f"    {change}")
    return "\n".join(out)

