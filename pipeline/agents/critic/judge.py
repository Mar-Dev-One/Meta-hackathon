"""The critic's judgment: Muse Spark vision scores a shot against the
rubric, with the measured numbers in front of it, and writes the fixes in
the storyboard's terms for the director to apply.

    shots = await measure(studio, sb, out_dir)
    critique = judge(sb, shots[0], profile)          # a Critique; critique.passed
    critique = judge(sb, shots[0], provider="meta")  # on Muse Spark instead of Muse Spark Open

Spark sees the shot's three frames, the brief, the shot's intent and its
storyboard (look, camera, titles), the brand, the shot grammar and the
measurements. It answers scores and issues; code adds the rest. The
measurements bind it: every major measured flag needs an issue in its
category and a score there of 6 or less, or the answer goes back with what
it missed, up to `tries` times. A shot passes when every score is 7 or more
and no major issue remains (decided in code, not by the model).

What the storyboard means to do is said, so it isn't judged a fault: a
reveal's product starting off frame, the lights fading up from dark, a
close-up cropping the product. Near the pass mark (a lowest score of 6 or
7) the same shot judged twice can land either side (a fifth of the time in
pipeline/agents/critic/compare.py's runs), so there it's judged once more,
as a new sample, and the worse of the two kept.

The critic runs on Muse Spark Open (Baseten) by default (CRITIC): as
consistent and as fast as Muse Spark in the comparison, and open weights.
"""

import json
import re

from PIL import Image
from pydantic import Field, ValidationError

from pipeline.agents.director import grammar
from pipeline.agents.director.write import _errors, _profile_text
from pipeline.meta import spark
from pipeline.schemas import BrandProfile, Critique, Issue, Scores, Storyboard
from pipeline.schemas.storyboard import Strict

from .measure import CROP, REVEALING, ShotMeasure, storyboard_colours

PASS = 7          # every score at least this
BOUND = 6         # a category with a major measured flag scores at most this
BORDER = (6, 7)   # lowest scores judged a second time
CRITIC = "baseten"   # the critic's model: "baseten" Muse Spark Open, "meta" Muse Spark


class CriticError(Exception):
    """No valid critique after every try; the last problems are in the message."""


class Verdict(Strict):
    """What Spark answers; the Critique is built from it."""
    scores: Scores
    issues: list[Issue] = Field(description="every problem worth fixing, the worst first; [] when there are none")


RUBRIC = """\
Score each category 0-10. Anchors:

- composition: 3 = the product off-balance or crowded by the frame's edge, dead space where it matters; 6 = centred
  and safe but flat, the negative space unused; 9 = deliberate placement (thirds or a strong centre), the space
  around it working for the shot's intent.
- lighting: 3 = the product's shape unreadable, its edges lost in the background, highlights blown or shadows
  crushed on it; 6 = it reads, but the light is flat or the separation weak in places; 9 = its form modelled by the
  light, every edge clear of the background, highlights shaped on glass and metal, the mood the brief asked for.
- product_visibility: 3 = cut by an edge, too small to read, or hidden; 6 = whole and visible but not the clear
  subject (the set competes, the label unreadable when it should read); 9 = whole, the obvious subject, its label
  and cap legible when the shot is about them.
- brand: 3 = colours or materials unlike the brand's, or something its do-not list rules out; 6 = right but
  generic; 9 = unmistakably this brand: its palette, materials and type.
- continuity: 3 = a different look from the ad's style (light, colour, mood); 6 = the same ad, with a jarring
  detail; 9 = of a piece with the style. (Cuts between shots are judged in the whole-ad pass.)
- titles: 3 = unreadable, over the product, or cut by the frame; 6 = readable but awkwardly placed or sized;
  9 = clean, well placed, in the brand's type. 10 when the shot has no title on screen.

Severity: major = a viewer would notice it as a mistake (a cut product, a lost silhouette, a title on the product,
the wrong mood for the brief); minor = a professional would fix it."""

SYSTEM = ("You are the critic of a studio that makes short 3D product adverts. You judge one shot from its rendered "
          "frames like an art director at a review: strict, specific and fair. Measurements from the renderer come "
          "with the frames; they are exact, so trust them over your eye for what they measure, and use your eye "
          "for everything else. Every fix you write is a change to the storyboard the director can make with the "
          "shot grammar. Answer in the schema.")

PROMPT = """# The brief

{brief}

Style: {style}.

# The shot

{shot_id}, {start:g} to {end:g} s of a {duration:g} s ad: "{intent}". The images are its frames at {times}
(its start, middle and end; {size} px previews of a {aspect} frame).

Its storyboard, the parts that set what you see (field paths as the director edits them):

{storyboard}{intended}

# The brand

{brand}

# Measured by the renderer

The product's exact pixels, from a render without it, in each frame:

{measured}

What the measurements flag (major ones must be answered):

{flags}

Meaning: fill = the product's share of the frame's height; edge_lost = the share of its outline that merges with
the background (Lab distance under 10 across it); separation = the difference in lightness between the product and
what's just around it (0-100); clipped / crushed = shares of its pixels blown to white / crushed to black; palette =
how far each storyboard colour is from the nearest colour rendered on the product (lightness counted at a third;
under 20 is a match, dark glass reads 20-30); title_overlap = the share of a title's box over the product.

# The rubric

{rubric}

# The shot grammar (what the director can change)

{grammar}

# Your answer

Scores for every category, and the issues: each with its severity, category, the time it shows, the problem in
concrete terms ("the cap's right edge merges with the wall"), and the fix as storyboard changes with their values
("look.lighting.intensity 1 -> 1.6", "shots[1].camera.fill 0.9 -> 0.65", "titles[0].y 0.8 -> 0.88"). One
problem per issue. No issue for something that is fine."""


def _storyboard_text(sb: Storyboard, index: int) -> str:
    shot = sb.shots[index]
    parts = {"look": sb.look.model_dump(by_alias=True, exclude_none=True),
             f"shots[{index}]": shot.model_dump(by_alias=True, exclude_none=True),
             "titles": [t.model_dump(exclude_none=True) for t in sb.titles],
             "tracks": [t.model_dump(exclude_none=True) for t in sb.tracks]}
    return json.dumps(parts, indent=1)


def intended(sb: Storyboard, index: int) -> list[str]:
    """What the storyboard means to happen in shot `index` that would look
    like a fault on its own (the measured checks exempt the same)."""
    shot, start = sb.shots[index], sb.shot_starts()[index]
    out = []
    if shot.camera.move == "reveal":
        arrived = start + REVEALING * shot.duration
        out.append(f"The move is a reveal: the camera's aim pans onto the product from {shot.camera.from_ or 'above'}, "
                   f"so until about {arrived:g} s it's meant to be off frame or cut. Judge its framing after that.")
    fade = sb.look.lighting.fade_in
    if fade and start < fade:
        out.append(f"The lights fade up from dark over the ad's first {fade:g} s (look.lighting.fade_in): until then a "
                   f"dark product is the reveal, not a lighting fault. Judge the light after that.")
    if shot.camera.max_fill() > CROP:
        out.append("The shot asks for fill over 0.97: a close-up that crops the product on purpose.")
    return out


def _intended_text(sb: Storyboard, index: int) -> str:
    """The intentions as a paragraph after the storyboard, or nothing (so
    shots without any keep the prompt they always had)."""
    notes = intended(sb, index)
    return "\n\nIntended, not faults:\n" + "\n".join(f"- {n}" for n in notes) if notes else ""


def _brand_text(sb: Storyboard, profile: BrandProfile | None) -> str:
    if profile:
        return _profile_text(profile)
    return json.dumps({"colours": storyboard_colours(sb), "note": "no brand profile: the storyboard's own colours "
                                                                  "and style stand for the brand"}, indent=1)


def _measured_text(m: ShotMeasure) -> str:
    lines = []
    for f in m.frames:
        if not f.fill_area:
            lines.append(f"- t={f.time:g}: the product isn't seen (in frame: {bool(f.bounds.get('in_view'))})")
            continue
        lines.append(f"- t={f.time:g}: fill {f.fill_height:.2f}, cut by {f.cut_by or 'nothing'}, centre "
                     f"({f.center[0]:.2f}, {f.center[1]:.2f}), headroom {f.headroom:.2f}, edge_lost "
                     f"{f.edge_lost:.2f} (median contrast {f.edge_contrast:.0f}), separation "
                     f"{abs(f.product_l - f.background_l):.0f} (product L {f.product_l:.0f}, around "
                     f"{f.background_l:.0f}), clipped {f.clipped:.3f}, crushed {f.crushed:.3f}, palette "
                     f"{json.dumps(f.palette)}, title_overlap {json.dumps(f.title_overlap)}")
    return "\n".join(lines)


def _flags_text(m: ShotMeasure) -> str:
    return "\n".join(f"- {f.severity} {f.category} at {f.time:g} s: {f.problem}" for f in m.flags) or "- none"


REPEAT = re.compile(r"^\s*(the\s+)?same\b", re.IGNORECASE)   # "same fix as above", "same as t=0.3s: ..."


def distinct(issues: list[Issue]) -> list[Issue]:
    """The issues without repeats: one written again for another frame
    ("same fix as above"), or the same fix in the same category. Muse Spark
    Open writes one issue per frame."""
    out, seen = [], set()
    for i in issues:
        key = (i.category, i.fix.strip().lower())
        if REPEAT.match(i.fix) or REPEAT.match(i.problem) or key in seen:
            continue
        seen.add(key)
        out.append(i)
    return out


def unanswered(verdict: Verdict, m: ShotMeasure) -> list[str]:
    """The major measured flags the verdict doesn't answer: no issue in the
    flag's category, or a score there above BOUND."""
    out = []
    for category in sorted({f.category for f in m.flags if f.severity == "major"}):
        problems = "; ".join(f.problem for f in m.flags if f.severity == "major" and f.category == category)
        if not any(i.category == category for i in verdict.issues):
            out.append(f"measured, major, and not in your issues: {category}: {problems}")
        score = getattr(verdict.scores, category)
        if score > BOUND:
            out.append(f"{category} scored {score} despite a major measured flag ({problems}): at most {BOUND}")
    return out


def _low(c) -> int:
    return min(c.scores.model_dump().values())


def worse(a, b):
    """Of two critiques of the same thing, the one that's harder on it:
    failing over passing, then the lower lowest score."""
    return min((a, b), key=lambda c: (c.passed, _low(c)))


def judge(sb: Storyboard, m: ShotMeasure, profile: BrandProfile | None = None, *, iteration: int = 0,
          provider: str = CRITIC, tries: int = 3, run=None, sample: int = 0,
          second_opinion: bool = True) -> Critique:
    """The critique of the measured shot `m` of `sb`; near the pass mark,
    the worse of two (second_opinion). With a run, every answer and what was
    wrong with it is logged, and the critique saved. `sample` judges it as a
    new sample (spark.ask), for measuring how much the critic varies."""
    critique = _judge_once(sb, m, profile, iteration=iteration, provider=provider, tries=tries, run=run,
                           sample=sample)
    if second_opinion and _low(critique) in BORDER:
        other = _judge_once(sb, m, profile, iteration=iteration, provider=provider, tries=tries, run=run,
                            sample=sample + 1)
        kept = worse(critique, other)
        if run:
            run.event("second_opinion", shot=m.shot, iteration=iteration,
                      first={"passed": critique.passed, "low": _low(critique)},
                      second={"passed": other.passed, "low": _low(other)},
                      kept="first" if kept is critique else "second")
        critique = kept
    if run:
        run.save_json(f"critiques/{m.shot}.{iteration}.json", critique)
        run.event("critique", shot=m.shot, iteration=iteration, passed=critique.passed,
                  scores=critique.scores.model_dump(), majors=sum(i.severity == "major" for i in critique.issues),
                  issues=len(critique.issues))
    return critique


def _judge_once(sb: Storyboard, m: ShotMeasure, profile: BrandProfile | None, *, iteration: int, provider: str,
                tries: int, run, sample: int) -> Critique:
    """One critique: the model's answer, sent back until it's valid."""
    index = next(i for i, s in enumerate(sb.shots) if s.id == m.shot)
    shot, start = sb.shots[index], sb.shot_starts()[index]
    frames = [f.path for f in m.frames]
    size = "x".join(str(n) for n in _image_size(frames[0]))
    prompt = PROMPT.format(brief=sb.brief, style=sb.style, shot_id=shot.id, start=start, end=start + shot.duration,
                           duration=sb.duration, intent=shot.intent, times=", ".join(f"{f.time:g} s" for f in m.frames),
                           size=size, aspect=sb.aspect, storyboard=_storyboard_text(sb, index),
                           intended=_intended_text(sb, index),
                           brand=_brand_text(sb, profile), measured=_measured_text(m), flags=_flags_text(m),
                           rubric=RUBRIC, grammar=grammar.load())
    schema = {**Verdict.model_json_schema(), "title": "Verdict"}
    feedback, found = "", []
    for attempt in range(1, tries + 1):
        answer = spark.ask(prompt + feedback, images=frames, schema=schema, system=SYSTEM, provider=provider,
                           sample=sample)
        try:
            verdict = Verdict.model_validate(answer.data)
            verdict.issues = distinct(verdict.issues)
        except ValidationError as e:
            found = _errors(e)
        else:
            found = unanswered(verdict, m)
        if run:
            run.event("critique_draft", shot=shot.id, iteration=iteration, attempt=attempt, problems=found,
                      cached=answer.cached, model=answer.model, answer=answer.data)
        if not found:
            break
        feedback = ("\n\n# Your previous answer\n\n" + answer.text +
                    "\n\n# What's wrong with it\n\n" + "\n".join(f"- {p}" for p in found) +
                    "\n\nAnswer again with these fixed, keeping what was right.")
    else:
        raise CriticError(f"no valid critique of {shot.id} after {tries} tries: " + "; ".join(found))

    scores = verdict.scores.model_dump()
    passed = min(scores.values()) >= PASS and not any(i.severity == "major" for i in verdict.issues)
    return Critique(shot=shot.id, iteration=iteration, frames=[f.time for f in m.frames], scores=verdict.scores,
                    passed=passed, issues=verdict.issues, measured=m.summary())


def _image_size(path: str) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size
