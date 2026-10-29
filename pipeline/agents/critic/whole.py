"""The critic's whole-ad pass: do the shots work as one ad? Muse Spark
vision sees a filmstrip and every cut, with the cuts' measurements, and
scores pacing, continuity, the arc and the brand. The shots are judged one
by one by judge.py; this is what none of them can see alone (a shot can be
good on its own and still cut badly from the one before).

    cuts = await measure_cuts(studio, sb, out_dir)
    ad = judge_ad(sb, shots, cuts, profile, out_dir=out_dir)     # an AdCritique; ad.passed

Two images: the filmstrip (a row per shot: its start, middle and end, as
measure.py rendered them) and the cuts (the last frame before each cut next
to the first after). As with a shot, the measurements bind it: every major
measured cut flag needs a continuity issue and a continuity score of 6 or
less, or the answer goes back, up to `tries` times. It passes when every
score is 7 or more and no major issue remains (decided in code). As with a
shot (judge.py), what the storyboard means to do is said (a reveal from
dark is an opening, not a slow start), and near the pass mark it's judged
twice and the worse kept.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import Field, ValidationError

from pipeline.agents.director import grammar
from pipeline.agents.director.write import _errors
from pipeline.meta import spark
from pipeline.schemas import AdCritique, AdIssue, AdScores, BrandProfile, Storyboard
from pipeline.schemas.storyboard import Strict

from .cuts import Cut
from .judge import BORDER, BOUND, CRITIC, PASS, CriticError, _brand_text, _low, intended, worse
from .measure import ShotMeasure

THUMB = 300          # pixels, the longer side of each frame in the images


class AdVerdict(Strict):
    """What Spark answers; the AdCritique is built from it."""
    scores: AdScores
    issues: list[AdIssue] = Field(description="every problem worth fixing, the worst first; [] when there are none")


RUBRIC = """\
Score each category 0-10. Anchors:

- pacing: 3 = shot lengths fight the brief (a slow luxury ad cut like a trailer, or an energetic one that drags);
  6 = even but monotonous, every shot the same length and speed; 9 = the rhythm of the brief: lengths and moves
  that build to the hero, cuts landing on motion.
- continuity: 3 = a cut feels like another ad (the light or its colour changes, the product swings to its back);
  6 = the same ad, with a cut that jolts (a big jump in angle or size for no reason); 9 = every cut flows: the
  same light and set, the product's side kept, consecutive shots moving differently.
- arc: 3 = no shape: the product unclear at the start, or the ad ends without the hero and the name; 6 = opens
  and closes right, the middle aimless; 9 = opens strong (the product readable in the first 2 s), each shot adds
  something (the label, the cap, the material), lands on the hero with the name.
- brand: 3 = the shots together feel like another brand; 6 = right but generic; 9 = unmistakably this brand from
  the first frame to the last.

Severity: major = a viewer would feel it as a mistake; minor = a professional would fix it."""

SYSTEM = ("You are the critic of a studio that makes short 3D product adverts. Each shot is judged on its own "
          "elsewhere; you judge whether together they make one good ad, like an editor at a review: strict, "
          "specific and fair. Measurements from the renderer come with the images; they are exact, so trust them over your eye "
          "for what they measure. Every fix you write is a change to the storyboard the director can make with "
          "the shot grammar. Answer in the schema.")

PROMPT = """# The brief

{brief}

Style: {style}. {duration:g} seconds, {aspect}.

# The ad

The first image is a filmstrip: a row per shot, its start, middle and end. The second shows each cut: the last
frame before it (left) and the first after it (right).

The shots, in order:

{outline}{intended}

Titles: {titles}

Other animation (tracks): {tracks}

# The brand

{brand}

# The cuts, measured by the renderer

{cuts}

What the measurements flag (major ones must be answered):

{flags}

Meaning: view = the side of the product facing the camera, in degrees around it from its front (its own spin
counted); lights x = the set's total light after the cut over before; light colour = how far the lights' colour
moves (Lab); frame light and colour = the same for the frame's pixels (they move with the framing too, so read
them with the images); size x = the product's height in the frame after over before.

# The rubric

{rubric}

# The shot grammar (what the director can change)

{grammar}

# Your answer

Scores for every category, and the issues: each with its severity, category, where (a shot 's2', a cut 's2->s3',
or 'all'), the problem in concrete terms, and the fix as storyboard changes with their values
("shots[2].camera.azimuth 160 -> 30", "shots[1].duration 1.2 -> 2", "tracks[0].keys[1].t 6.5 -> 4", or
"remove tracks[1]" when an animation itself is the problem: what it animates then keeps its look's value). One
problem per issue. No issue for something that is fine. Each shot is judged on its own elsewhere: judge how
they work together (the cuts, the order, the rhythm, the arc), not each shot's own craft."""


def _label(img: Image.Image, text: str) -> Image.Image:
    img = img.copy()
    img.thumbnail((THUMB, THUMB))
    tile = Image.new("RGB", (img.width, img.height + 18), (20, 20, 22))
    tile.paste(img, (0, 18))
    ImageDraw.Draw(tile).text((4, 3), text, fill=(235, 235, 235))
    return tile


def _grid(rows: list[list[Image.Image]], gap: int = 6) -> Image.Image:
    width = max(sum(t.width for t in r) + gap * (len(r) - 1) for r in rows)
    height = sum(max(t.height for t in r) for r in rows) + gap * (len(rows) - 1)
    out = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for r in rows:
        x = 0
        for t in r:
            out.paste(t, (x, y))
            x += t.width + gap
        y += max(t.height for t in r) + gap
    return out


def filmstrip(shots: list[ShotMeasure]) -> Image.Image:
    return _grid([[_label(Image.open(f.path).convert("RGB"), f"{s.shot}  {f.time:g} s") for f in s.frames]
                  for s in shots])


def cut_pairs(cuts: list[Cut]) -> Image.Image:
    return _grid([[_label(Image.open(c.frames[0]).convert("RGB"), f"{c.before}, last frame"),
                   _label(Image.open(c.frames[1]).convert("RGB"), f"{c.after}, first frame ({c.time:g} s)")]
                  for c in cuts])


def _outline(sb: Storyboard) -> str:
    lines = []
    for i, (start, shot) in enumerate(zip(sb.shot_starts(), sb.shots)):
        camera = shot.camera.model_dump(by_alias=True, exclude_none=True)
        lines.append(f"- shots[{i}] {shot.id}, {start:g}-{start + shot.duration:g} s ({shot.duration:g} s): "
                     f"\"{shot.intent}\"; camera {json.dumps(camera)}")
    return "\n".join(lines)


def _cuts_text(cuts: list[Cut]) -> str:
    return "\n".join(f"- {c.before}->{c.after} at {c.time:g} s: view {c.view[0]:.0f} -> {c.view[1]:.0f} "
                     f"({c.view_jump:+.0f}), lights x{c.set_light:g}, light colour {c.set_colour:g}, frame light "
                     f"{c.light_jump:+.1f}, frame colour {c.colour_jump:.1f}, size x{c.size_ratio:g}"
                     for c in cuts) or "- none (one shot)"


def unanswered(verdict: AdVerdict, cuts: list[Cut]) -> list[str]:
    """The major measured cut flags the verdict doesn't answer."""
    majors = [f.problem for c in cuts for f in c.flags if f.severity == "major"]
    if not majors:
        return []
    out = []
    if not any(i.category == "continuity" for i in verdict.issues):
        out.append("measured, major, and not in your issues: continuity: " + "; ".join(majors))
    if verdict.scores.continuity > BOUND:
        out.append(f"continuity scored {verdict.scores.continuity} despite major measured flags "
                   f"({'; '.join(majors)}): at most {BOUND}")
    return out


def _intended_text(sb: Storyboard) -> str:
    """Every shot's intentions (judge.intended), or nothing."""
    notes = [f"{shot.id}: {n}" for i, shot in enumerate(sb.shots) for n in intended(sb, i)]
    return "\n\nIntended, not faults:\n" + "\n".join(f"- {n}" for n in notes) if notes else ""


def judge_ad(sb: Storyboard, shots: list[ShotMeasure], cuts: list[Cut], profile: BrandProfile | None = None, *,
             out_dir: Path, iteration: int = 0, provider: str = CRITIC, tries: int = 3, run=None,
             second_opinion: bool = True) -> AdCritique:
    """The whole ad's critique, from its measured shots and cuts; near the
    pass mark, the worse of two. The two images are saved in `out_dir`
    (filmstrip.png, cuts.png)."""
    critique = _judge_ad_once(sb, shots, cuts, profile, out_dir=out_dir, iteration=iteration, provider=provider,
                              tries=tries, run=run, sample=0)
    if second_opinion and _low(critique) in BORDER:
        other = _judge_ad_once(sb, shots, cuts, profile, out_dir=out_dir, iteration=iteration, provider=provider,
                               tries=tries, run=run, sample=1)
        kept = worse(critique, other)
        if run:
            run.event("second_opinion", shot="ad", iteration=iteration,
                      first={"passed": critique.passed, "low": _low(critique)},
                      second={"passed": other.passed, "low": _low(other)},
                      kept="first" if kept is critique else "second")
        critique = kept
    if run:
        run.save_json(f"critiques/ad.{iteration}.json", critique)
        run.event("ad_critique", iteration=iteration, passed=critique.passed, scores=critique.scores.model_dump(),
                  majors=sum(i.severity == "major" for i in critique.issues), issues=len(critique.issues))
    return critique


def _judge_ad_once(sb: Storyboard, shots: list[ShotMeasure], cuts: list[Cut], profile: BrandProfile | None, *,
                   out_dir: Path, iteration: int, provider: str, tries: int, run, sample: int) -> AdCritique:
    """One critique of the whole ad: the model's answer, sent back until it's valid."""
    out_dir = Path(out_dir)
    strip, pairs = out_dir / "filmstrip.png", out_dir / "cuts.png"
    filmstrip(shots).save(strip)
    images = [strip]
    if cuts:
        cut_pairs(cuts).save(pairs)
        images.append(pairs)
    titles = "; ".join(f"titles[{i}] {t.text!r} from {t.start:g} s at y {t.y:g}" for i, t in enumerate(sb.titles))
    tracks = "; ".join(f"tracks[{i}] {t.entity}.{t.component}.{t.field} keys at "
                       f"{', '.join(f'{k.t:g}' for k in t.keys)} s" for i, t in enumerate(sb.tracks))
    flags = "\n".join(f"- {f.severity} at {f.time:g} s: {f.problem}" for c in cuts for f in c.flags) or "- none"
    prompt = PROMPT.format(brief=sb.brief, style=sb.style, duration=sb.duration, aspect=sb.aspect,
                           outline=_outline(sb), intended=_intended_text(sb), titles=titles or "none",
                           tracks=tracks or "none",
                           brand=_brand_text(sb, profile), cuts=_cuts_text(cuts), flags=flags, rubric=RUBRIC,
                           grammar=grammar.load())
    schema = {**AdVerdict.model_json_schema(), "title": "AdVerdict"}
    feedback, found = "", []
    for attempt in range(1, tries + 1):
        answer = spark.ask(prompt + feedback, images=images, schema=schema, system=SYSTEM, provider=provider,
                           sample=sample)
        try:
            verdict = AdVerdict.model_validate(answer.data)
        except ValidationError as e:
            found = _errors(e)
        else:
            found = unanswered(verdict, cuts)
        if run:
            run.event("ad_critique_draft", iteration=iteration, attempt=attempt, problems=found,
                      cached=answer.cached, model=answer.model, answer=answer.data)
        if not found:
            break
        feedback = ("\n\n# Your previous answer\n\n" + answer.text +
                    "\n\n# What's wrong with it\n\n" + "\n".join(f"- {p}" for p in found) +
                    "\n\nAnswer again with these fixed, keeping what was right.")
    else:
        raise CriticError(f"no valid critique of the whole ad after {tries} tries: " + "; ".join(found))

    scores = verdict.scores.model_dump()
    passed = min(scores.values()) >= PASS and not any(i.severity == "major" for i in verdict.issues)
    return AdCritique(iteration=iteration, scores=verdict.scores, passed=passed, issues=verdict.issues,
                      measured=[c.to_json() | {"flags": [f.problem for f in c.flags]} for c in cuts])
