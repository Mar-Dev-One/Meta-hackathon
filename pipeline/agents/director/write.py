"""Brief → storyboard: Muse Spark plans the ad from the brief, the brand
profile, the shot grammar and the style library; code checks it.

    sb = await write("luxury perfume ad, dark and moody, 15 seconds", profile, studio=studio, run=run)

Spark writes a Plan (a Storyboard without the product, which is the brand
profile's). It's validated by the schema and then checked in code against
the craft rules a schema can't hold (lengths add up, the ending is the hero
with the brand's name, titles fit the frame as the Studio measures them).
Whatever is wrong goes back to Spark with its answer, up to `tries` times.
"""

import json
import re
from typing import Literal

from pydantic import Field, ValidationError

from pipeline.meta import spark
from pipeline.schemas import BrandProfile, Storyboard
from pipeline.schemas.storyboard import Look, Product, Shot, Strict, Title, Track

from . import grammar
from .styles import STYLES

FRAMES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
DEFAULT_SECONDS = 15.0

SHOT_MIN, SHOT_MAX = 1.2, 5.0
HERO_MIN = 2.5            # the last shot, seconds
HERO_AZIMUTH = 25         # degrees from the front
TITLE_DELAY = 0.4         # the name appears at least this long after the hero starts
TITLE_SEEN = 0.8          # ... and at least this long before the end
MAX_TITLES = 2            # titles stay on once in, so this many are on screen together
TITLE_BANDS = ((0.0, 0.2), (0.72, 1.0))   # where a title's centre may be (above or below the product)
TITLE_CLEAR = 0.02        # of the frame's height between a title's box and the product (centred, `fill` tall)
PEDESTAL_WIDTH = (1.2, 7.0)   # a pedestal's width, in product widths: wider than it, not a dance floor
PEDESTAL_HEIGHT = 1.5         # at most this many product heights tall, or it upstages the product

# Templates' real sizes (height, width) in meters, as product.create makes them (Products.c).
TEMPLATE_SIZES = {"perfume": (0.12, 0.08), "bottle": (0.30, 0.075), "jar": (0.07, 0.09), "can": (0.122, 0.066),
                  "dropper": (0.11, 0.04)}


class DirectorError(Exception):
    """No valid storyboard after every try; the last problems are in the message."""


class Plan(Strict):
    title: str = Field(description="a working name for the ad")
    style: Literal[tuple(STYLES)] = Field(description="the style from the library it starts from")
    look: Look
    shots: list[Shot] = Field(min_length=2, max_length=12)
    titles: list[Title] = Field(max_length=MAX_TITLES)
    tracks: list[Track] = Field(default_factory=list, description="other animation, e.g. the product spinning")


SYSTEM = ("You are the director of a studio that makes short 3D product adverts. You plan an ad as shots for a "
          "renderer whose every option is in the shot grammar, and you only use what it offers. The brief comes "
          "first, then the brand profile and the ad-craft rules. Answer in the schema.")

PROMPT = """# The brief

{brief}

Length: {seconds:g} seconds. Frame: {aspect}.

# The brand profile (from its product photo)

{profile}

The product (its 3D shape, materials and label) is built from this profile; you plan everything around it,
sized for it (a pedestal a little wider than it and not much taller).

Its do_not list is the brand's usual taste: follow it, unless the brief asks for something it rules out (say,
a bright summer campaign for a brand that's usually muted). Then the brief wins, and the brand stays
recognisable through its name, its type and its palette's accents.

# The style library (whole looks; start from one, adapt its colours to the palette)

{styles}

{grammar}
# Your answer

A Plan: a working title, the style you start from, the look (set, light, environment), the shots in
order (their durations adding up to {seconds:g} s), the titles and any extra animation."""


def seconds_in(brief: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s\b|sec\b|secs\b|seconds?\b)", brief, re.IGNORECASE)
    return float(m.group(1)) if m else None


def aspect_in(brief: str) -> str:
    text = brief.lower()
    if any(w in text for w in ("vertical", "9:16", "portrait", "reel", "story", "stories", "tiktok", "shorts")):
        return "9:16"
    if any(w in text for w in ("square", "1:1")):
        return "1:1"
    return "16:9"


def product_size(product: Product) -> tuple[float, float]:
    """The product's height and width in meters, as the Studio builds it."""
    if product.profile_parts:
        points = [pt for part in product.profile_parts for pt in part.profile]
        return max(y for _, y in points), 2 * max(r for r, _ in points)
    height, width = TEMPLATE_SIZES[product.template]
    return product.height or height, product.width or width


def _profile_text(p: BrandProfile) -> str:
    height, width = product_size(p.product())
    facts = {"brand": p.brand, "product_name": p.product_name, "category": p.category,
             "size": f"{height * 100:.1f} cm tall, {width * 100:.1f} cm wide",
             "materials": [f"{m.name}: {m.looks_like} ({m.color})" for m in p.materials],
             "palette": [f"{s.hex} {s.role} {s.share:.0%}" for s in p.palette],
             "typography": p.typography.model_dump(), "mood": p.mood, "do_not": p.do_not,
             "label": f"wraps {p.label.arc:g} degrees round the body" if p.label else "none"}
    return json.dumps(facts, indent=1)


def _styles_text() -> str:
    return "\n".join(json.dumps({"name": s.name, "use_for": s.use_for, "look": s.look.model_dump(exclude_none=True),
                                 "title": s.title.model_dump(), "shot_seconds": s.shot_seconds, "moves": s.moves,
                                 "ease": s.ease, "aperture": s.aperture}, separators=(",", ":")) for s in STYLES.values())


def assemble(plan: Plan, profile: BrandProfile, brief: str, aspect: str) -> Storyboard:
    data = plan.model_dump(by_alias=True, exclude_none=True)
    data.update(brief=brief, aspect=aspect, product=profile.product().model_dump(by_alias=True))
    return Storyboard.model_validate(data)


def problems(sb: Storyboard, profile: BrandProfile, seconds: float) -> list[str]:
    """The craft rules in code: what's wrong with the storyboard, each said
    so it can be fixed."""
    out = []
    if abs(sb.duration - seconds) > 0.5:
        out.append(f"the shots add up to {sb.duration:g} s, but the ad is {seconds:g} s: change their durations")
    for shot in sb.shots:
        if not SHOT_MIN <= shot.duration <= SHOT_MAX:
            out.append(f"shot {shot.id} lasts {shot.duration:g} s: keep shots between {SHOT_MIN:g} and {SHOT_MAX:g} s")
    for a, b in zip(sb.shots, sb.shots[1:]):
        if a.camera.move == b.camera.move:
            out.append(f"shots {a.id} and {b.id} are both {a.camera.move}: consecutive shots move differently")

    hero, hero_start = sb.shots[-1], sb.shot_starts()[-1]
    if hero.camera.move != "static" or abs(hero.camera.azimuth) > HERO_AZIMUTH or hero.duration < HERO_MIN:
        out.append(f"the last shot ({hero.id}) must be the hero: a static move from the front (azimuth within "
                   f"{HERO_AZIMUTH} degrees of 0), at least {HERO_MIN:g} s long")

    if profile.brand:
        brand = profile.brand.casefold().replace(" ", "")
        named = [t for t in sb.titles if brand in t.text.casefold().replace(" ", "")]
        if not named:
            out.append(f"no title shows the brand name {profile.brand!r}")
        elif not any(hero_start + TITLE_DELAY <= t.start <= sb.duration - TITLE_SEEN for t in named):
            out.append(f"the brand name's title must start in the hero shot, between {hero_start + TITLE_DELAY:g} s "
                       f"and {sb.duration - TITLE_SEEN:g} s")
    for t in sb.titles:
        if t.font == "script" and t.text.isupper():
            out.append(f"title {t.text!r} is script in capitals: write it in mixed case, or use another font")
        if not any(lo <= t.y <= hi for lo, hi in TITLE_BANDS):
            out.append(f"title {t.text!r} is centred at y {t.y:g}, over the product: put it at y 0.72-0.95 "
                       f"(below) or 0.05-0.2 (above)")
    if sb.look.pedestal:
        height, width = product_size(sb.product)
        ped = sb.look.pedestal
        lo, hi = PEDESTAL_WIDTH
        if not lo * width <= ped.width <= hi * width or ped.height > PEDESTAL_HEIGHT * height:
            out.append(f"the pedestal ({ped.width * 100:.0f} cm wide, {ped.height * 100:.0f} cm tall) is out of "
                       f"proportion with the product ({width * 100:.1f} cm wide, {height * 100:.1f} cm tall): make it "
                       f"{lo * width * 100:.0f}-{hi * width * 100:.0f} cm wide and at most "
                       f"{PEDESTAL_HEIGHT * height * 100:.0f} cm tall (about {2.5 * width * 100:.0f} x "
                       f"{0.6 * height * 100:.0f} cm suits most), or set it to null")
    for track in sb.tracks:
        if track.entity != "product" and not track.entity.startswith("light_"):
            out.append(f"a track animates {track.entity!r}: tracks may only animate the product or the lights")
        if any(k.t > sb.duration for k in track.keys):
            out.append(f"a track on {track.entity} has keys after the end ({sb.duration:g} s)")
    return out


def shot_at(sb: Storyboard, t: float) -> Shot:
    """The shot on screen at `t` seconds."""
    for start, shot in zip(sb.shot_starts(), sb.shots):
        if t < start + shot.duration:
            return shot
    return sb.shots[-1]


async def title_problems(studio, sb: Storyboard) -> list[str]:
    """Titles that don't fit the frame, overlap each other or the product
    (centred in the frame, `fill` of its height in the shot the title
    appears in), as the Studio measures them at the ad's frame size (placed
    as build() places them)."""
    width, height = FRAMES[sb.aspect]
    out, boxes = [], []
    for t in sb.titles:
        m = await studio.call("text.measure", text=t.text, font=t.font, size=t.size, anchor="center",
                              offset=[0, t.y - 0.5], tracking=t.tracking, width=width, height=height)
        x, y, w, h = m["box"]
        if not m["fits"]:
            out.append(f"title {t.text!r} doesn't fit the {sb.aspect} frame ({w:.0%} of its width): "
                       f"make it smaller or its tracking tighter")
        for other, (ox, oy, ow, oh) in boxes:
            if y < oy + oh and oy < y + h and x < ox + ow and ox < x + w:
                out.append(f"titles {other!r} and {t.text!r} overlap: move them apart vertically")
        boxes.append((t.text, (x, y, w, h)))
        shot = shot_at(sb, t.start)
        fill = max(f for f in (shot.camera.fill, shot.camera.from_fill, shot.camera.to_fill) if f is not None)
        top, bottom = 0.5 - 0.5 * fill - TITLE_CLEAR, 0.5 + 0.5 * fill + TITLE_CLEAR
        if y < bottom and top < y + h:
            out.append(f"title {t.text!r} (y {y:.2f} to {y + h:.2f} of the frame) is over the product, which "
                       f"fills {top + TITLE_CLEAR:.2f} to {bottom - TITLE_CLEAR:.2f} in {shot.id} (fill {fill:g}): "
                       f"lower that shot's fill or move the title clear of it")
    return out


def _errors(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]


async def write(brief: str, profile: BrandProfile, *, studio=None, run=None, seconds: float | None = None,
                aspect: str | None = None, tries: int = 3) -> Storyboard:
    """The storyboard for `brief` (its length and frame read from it unless
    given). With a Studio, titles are measured too; with a run, every draft
    and its problems are logged and the result saved as storyboard.json."""
    seconds = seconds or seconds_in(brief) or DEFAULT_SECONDS
    aspect = aspect or aspect_in(brief)
    prompt = PROMPT.format(brief=brief, seconds=seconds, aspect=aspect, profile=_profile_text(profile),
                           styles=_styles_text(), grammar=grammar.load())
    schema = {**Plan.model_json_schema(), "title": "Plan"}
    feedback, found = "", []
    for attempt in range(1, tries + 1):
        answer = spark.ask(prompt + feedback, schema=schema, system=SYSTEM)
        try:
            plan = Plan.model_validate(answer.data)
            sb = assemble(plan, profile, brief, aspect)
        except ValidationError as e:
            found = _errors(e)
        else:
            found = problems(sb, profile, seconds) + (await title_problems(studio, sb) if studio else [])
        if run:
            run.event("draft", attempt=attempt, problems=found, cached=answer.cached)
        if not found:
            if run:
                run.output("storyboard", run.save_json("storyboard.json", sb))
            return sb
        feedback = ("\n\n# Your previous answer\n\n" + answer.text +
                    "\n\n# What's wrong with it\n\n" + "\n".join(f"- {p}" for p in found) +
                    "\n\nAnswer again with all of these fixed, keeping what was right.")
    raise DirectorError(f"no valid storyboard after {tries} tries: " + "; ".join(found))


if __name__ == "__main__":
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    from pipeline.runs import RUNS, Run
    from pipeline.studio import Studio, build, preview, render

    # Briefs for the brand analyst's three test products (their newest profiles in runs/).
    BRIEFS = {
        "aurelle_perfume": "Luxury perfume ad, dark and moody, 15 seconds.",
        "solana_oil": "Olive oil from a small family grove: warm, natural and honest. 12 seconds.",
        "mira_jar": "Face cream launch for Instagram Reels: clean, calm and bright, vertical, 10 seconds.",
    }

    def profile_of(photo: str) -> BrandProfile:
        found = sorted(RUNS.glob(f"*-analyse-{photo}/brand_profile.json"))
        if not found:
            sys.exit(f"no brand profile for {photo}: run python -m pipeline.agents.analyst first")
        return BrandProfile.model_validate_json(found[-1].read_text(encoding="utf-8"))

    async def main(names: list[str], frames: bool, video: bool, short: int) -> None:
        async with Studio() as studio:
            for name in names:
                profile = profile_of(name)
                with Run.create(f"director-{name}") as run:
                    run.watch(studio)
                    run.event("brief", text=BRIEFS[name], brand=profile.brand)
                    sb = await write(BRIEFS[name], profile, studio=studio, run=run)
                    if frames or video:
                        await build(studio, sb)
                    if frames:
                        await preview(studio, run, sb)
                    if video:
                        await render(studio, run, sb, name, short=short)
                drafts = sum(1 for line in (run.root / "log.jsonl").read_text().splitlines() if '"draft"' in line)
                print(f"\n{name}: {sb.title!r}, style {sb.style}, {sb.aspect}, {sb.duration:g} s, {drafts} draft(s)")
                for start, shot in zip(sb.shot_starts(), sb.shots):
                    print(f"  {start:5.1f}s {shot.id} {shot.camera.move:7} {shot.duration:g}s  {shot.intent}")
                for t in sb.titles:
                    print(f"  title {t.text!r} {t.font} {t.color} at {t.start:g}s, y {t.y:g}")
                print(f"  {Path(run.root).name}")

    parser = argparse.ArgumentParser(description="Storyboards for the test briefs, written by the director; "
                                                 "optionally rendered.")
    parser.add_argument("products", nargs="*", help=f"which (default all): {', '.join(BRIEFS)}")
    parser.add_argument("--preview", action="store_true", help="also render a few frames")
    parser.add_argument("--video", action="store_true", help="also render the video")
    parser.add_argument("--size", type=int, default=1080, help="the video's shorter side in pixels")
    args = parser.parse_args()
    asyncio.run(main(args.products or list(BRIEFS), args.preview, args.video, args.size))
