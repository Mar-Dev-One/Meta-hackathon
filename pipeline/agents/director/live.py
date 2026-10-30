"""The live director: Muse Spark makes the ad in the Studio itself, with every
command the Studio has (pipeline.studio.tools), not by filling in a
storyboard. It decides the set, the props, the light, the cameras, the
animation and the titles, looks at its previews, changes what it doesn't
like, and declares its cut when it's done.

    cut = await direct(studio, run, brief, profile, aspect="16:9")
    cut.shots          # [{"start", "end", "intent"}], back to back from 0
    cut.duration, cut.mood
    verdict = await review(studio, run, cut, brief, profile)      # Spark judges frames of its film
    cut = await revise(studio, run, cut, verdict, brief, profile)  # and fixes it in the Studio
    vertical = await adapt(studio, run, cut, "9:16", brief, profile)   # the same film re-shot for 9:16
    video = await render_cut(studio, run, cut, "aurelle")         # final/aurelle_16x9.mp4, with music

Two tools sit beside the commands: make_product (the brand's own product,
the traced shape or the dressed 3D model, which is too much data to type
into product.create) and finish (the cut: the shots, the music's mood).
The product is always the entity "product", which the critic measures.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from pipeline.encode import finish as finish_video
from pipeline.encode.music import MOODS as MOOD_WORDS, music
from pipeline.meta import spark
from pipeline.meta.client import MetaError
from pipeline.runs import Run
from pipeline.schemas import BrandProfile
from pipeline.studio import PRODUCT, StudioError, StudioTimeout
from pipeline.studio.build import ASPECTS, create_product, place_product_model
from pipeline.studio.render import RENDER_PER_FRAME, RENDER_SETUP, frame_size
from pipeline.studio.tools import Bridge

MOODS = ("dark", "calm", "energetic", "warm")   # the music (pipeline.encode.music)
PREVIEW_SHORT = 360                             # previews' shorter side in pixels
MAKERS = ("product.create", "place_model", "entity.create", "backdrop.create", "entity.update")   # name an entity
PASS = 7          # the review passes when every score is at least this
FPS = 30


@dataclass
class Cut:
    shots: list[dict]                   # {"start", "end", "intent"} in seconds
    mood: str
    summary: str
    aspect: str
    calls: list[dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(s["end"] for s in self.shots)


SYSTEM = """You are the director, set designer, lighting artist, camera operator and editor of a premium
CGI product film, all at once. You make it yourself in a 3D studio by calling its commands: every
command it has is a tool. Nothing is decided for you. You choose the set (backdrop, pedestal, floor,
surfaces, props, or none), the light (presets, or your own lights placed and coloured one by one),
the environment (HDRI, exposure, bloom, tone mapping), every camera and how it moves, what animates
and how (any field of any entity, on the timeline), the titles, the cuts and the length.

How the studio works:
- Meters, Y up. The product stands where you put it; the camera's front is +Z by default.
- commands.list and components.describe tell you every command and every field; entity.get and
  scene.describe show what's there. Colours in components are linear RGB 0-1; in product, backdrop
  and text commands they're "#RRGGBB".
- make_product is the only way to put the brand's product in the scene: its real shape and label
  (or its real 3D model), at its real size, as the entity "product". Never build the product
  yourself with product.create or place_model (those are for other objects: props, a vase, a
  stone), and keep the name "product" for it alone: the film is about it, and it's measured by it.
- The timeline is the film: time 0 is its first frame. camera.move writes a shot's camera keys in
  its own time range (start, duration), so moves placed end to end are cuts; pass the frame's
  aspect to it. Or place your own camera (camera.set) and animate its Transform with
  timeline.set_track. Anything can be animated the same way: lights, the product, props, exposure.
- shot.preview renders frames at the times you give: you see them. Preview at the frame size you
  are given, at least once per shot, and look hard: is the product clear, well lit, well framed,
  the right size, never cut off by accident? Are titles readable, clear of the product? Fix what
  isn't right and preview again.
- history.undo undoes your last change; batch runs several studio commands as one (make_product and
  finish are tools of their own: call them alone, never inside a batch).
- Sizes are real, in meters: the product is as tall as the brand says. Build the set in proportion
  to it (a pedestal a little wider than the product, not a stage around it), and frame it so the
  product is the hero of every shot, not lost in the set.
- You have a limited number of turns (you're told how many). Work efficiently: call several tools in
  one turn whenever they don't depend on each other's results, and don't re-read what you know.

Make it look like a real, expensive product film: considered composition, light that shapes the
product and separates it from the background, purposeful camera movement, nothing cheap or
cluttered. Respect the brand: its colours, its mood, what it must avoid.

When the film is done, call finish with its shots (back to back from 0, each with what it's for),
the music's mood and a sentence about the film. Then answer in one sentence."""


def _brand(profile: BrandProfile) -> str:
    brand = profile.model_dump(include={"brand", "product_name", "category", "height", "palette", "materials",
                                        "typography", "mood", "do_not"}, exclude_none=True)
    shape = "a 3D model of it" if profile.model else "its shape traced from its photo, with its label"
    return f"""The brand, as read from the product's photo (the product is {shape}; make_product puts it in the
scene):
{json.dumps(brand, indent=1)}"""


def _frame(aspect: str) -> str:
    w, h = frame_size(aspect, PREVIEW_SHORT)
    return f"The frame is {aspect} (aspect {ASPECTS[aspect]:.4f}); preview at {w}x{h}."


def _prompt(brief: str, profile: BrandProfile, aspect: str) -> str:
    return f"""The brief: {brief}

{_frame(aspect)}

{_brand(profile)}

The stage is empty. Make the film."""


def _as_it_is(cut: "Cut") -> str:
    return f"""Your film is in the studio as you left it: {cut.summary}
Its shots: {json.dumps(cut.shots)}; the music's mood: {cut.mood}.
scene.describe, timeline.get and text.get show everything in it."""


def _tools(studio, profile: BrandProfile, finished: dict) -> dict:
    async def make_product(args: dict) -> dict:
        if args.get("on_top_of"):
            await studio.call("entity.get", entity=args["on_top_of"])   # there to stand on, before anything changes
        product = profile.product()
        top = float((args.get("position") or [0, 0, 0])[1])
        if any(e.get("name") == PRODUCT for e in (await studio.call("scene.describe")).get("entities", [])):
            await studio.call("entity.destroy", entity=PRODUCT)
        if product.model:
            await place_product_model(studio, product, top)
        else:
            await create_product(studio, product, top)
        finished["made"] = True
        position = args.get("position") or [0, 0, 0]
        if args.get("on_top_of"):
            await studio.call("entity.place", entity=PRODUCT, relative_to={"entity": args["on_top_of"], "side": "on_top"})
        elif position[0] or position[2]:
            await studio.call("entity.place", entity=PRODUCT, position=position)
        return await studio.call("entity.get", entity=PRODUCT)

    async def finish(args: dict) -> dict:
        shots, end = [], 0.0
        for s in args.get("shots") or []:   # a shot without a start starts where the one before ends
            if s.get("end") is None:
                return {"error": "every shot needs its end (seconds)"}
            shots.append({"start": s.get("start", end), "end": s["end"], "intent": s.get("intent", "")})
            end = s["end"]
        shots.sort(key=lambda s: s["start"])
        problems = []
        if not shots:
            problems.append("no shots")
        for a, b in zip(shots, shots[1:]):
            if abs(a["end"] - b["start"]) > 1e-3:
                problems.append(f"shots must be back to back: one ends at {a['end']}, the next starts at {b['start']}")
        if shots and shots[0]["start"] != 0:
            problems.append("the first shot must start at 0")
        try:
            await studio.call("entity.get", entity=PRODUCT)
        except StudioError:
            finished.pop("made", None)   # reset or cleared away since
        if not finished.get("made"):
            problems.append("the brand's product isn't in the film: put it in with make_product")
        if args.get("mood") not in MOODS:
            problems.append(f"mood must be one of {', '.join(MOODS)}")
        if problems:
            return {"error": "; ".join(problems)}
        finished.update(shots=shots, mood=args["mood"], summary=args.get("summary", ""))
        return {"ok": True, "duration": shots[-1]["end"]}

    return {
        "make_product": ({"type": "function", "name": "make_product",
                          "description": "Puts the brand's product in the scene as the entity \"product\" (replacing it if "
                                         "it's there), at its real size, its base at `position` (default the origin), or "
                                         "standing on top of the entity `on_top_of`. Returns the entity.",
                          "parameters": {"type": "object", "properties": {
                              "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                              "on_top_of": {"type": "string", "description": "an entity's name, e.g. a pedestal"}},
                              "required": []}}, make_product),
        "finish": ({"type": "function", "name": "finish",
                    "description": "Declares the film done: its shots in order, back to back from 0, the music's mood and "
                                   "a sentence about the film.",
                    "parameters": {"type": "object", "properties": {
                        "shots": {"type": "array", "items": {"type": "object", "properties": {
                            "start": {"type": "number"}, "end": {"type": "number"},
                            "intent": {"type": "string", "description": "what the shot is for"}},
                            "required": ["start", "end", "intent"]}},
                        "mood": {"type": "string", "enum": list(MOODS)},
                        "summary": {"type": "string"}},
                        "required": ["shots", "mood", "summary"]}}, finish),
    }


def _shots_made(calls: list[dict], previous: Cut | None) -> list[dict]:
    """The cut as Spark's camera moves say it is (each camera.move a shot
    from its start for its duration, a later one at the same start replacing
    it; `previous`'s shots where it made none), back to back; the intents
    from `previous`, shot by shot."""
    ranges = {round(s["start"], 3): s["end"] for s in previous.shots} if previous else {}
    for c in calls:
        if c["command"] == "camera.move" and not (isinstance(c["result"], dict) and c["result"].get("error")):
            start = round(float(c["args"].get("start", 0)), 3)
            ranges[start] = start + float(c["args"].get("duration", 0))
    starts = sorted(ranges)
    ends = starts[1:] + [ranges[starts[-1]]] if starts else []
    shots = [{"start": a, "end": b, "intent": previous.shots[i]["intent"] if previous and i < len(previous.shots)
              else f"shot {i + 1}"} for i, (a, b) in enumerate(zip(starts, ends))]
    return [s for s in shots if s["end"] > s["start"]]


def _mood(text: str) -> str:
    """The music's mood whose words come up most in `text` (pipeline.encode.music's), "calm" if none."""
    found = {mood: sum(word in text.lower() for word in words) for mood, words in MOOD_WORDS.items()}
    best = max(found, key=found.get)
    return best if found[best] else "calm"


def _refuse(command: str, args: dict) -> str | None:
    """Turns down any command but make_product making an entity called "product"."""
    if command in MAKERS and args.get("name") == PRODUCT:
        return (f"{command} can't make the entity \"{PRODUCT}\": the brand's product comes only from make_product "
                "(its real shape and label, or its real model). Give other objects other names.")
    return None


async def _session(studio, run: Run, prompt: str, profile: BrandProfile, aspect: str, label: str,
                   made: bool = False, max_turns: int = 50, previous: Cut | None = None) -> Cut:
    """One working session of Spark's in the Studio, ending with finish: its
    cut (live/<label>.json), its previews in live/<label>/, every command it
    ran in the run's log ("tool" events). If Spark runs out of turns before
    finish, the film stays as it left it and the cut is read from its camera
    moves (the intents and mood from `previous`, the cut it was changing)."""
    finished: dict = {"made": True} if made else {}

    def logged(command: str, args: dict, result) -> None:
        error = result.get("error") if isinstance(result, dict) else None
        run.event("tool", session=label, command=command, args=args, error=error)

    bridge = await Bridge.open(studio, on_call=logged, extra=_tools(studio, profile, finished),
                               previews=run.folder("live", label), refuse=_refuse)
    reminders = {left: f"{left} turns left. Wrap up: fix only what matters most, preview once more, then call finish."
                 for left in (10, 5)} | {2: "2 turns left: call finish now with the film's shots as they are."}
    try:
        result = await bridge.run(f"{prompt}\n\nYou have {max_turns} turns.", system=SYSTEM, max_turns=max_turns,
                                  reminders=reminders, last_tools=["finish"])
        said = result.text
    except MetaError as e:   # out of turns: the film is in the Studio as Spark left it
        said = str(e)
        run.event("unfinished", session=label, error=said)
    if "shots" not in finished:
        shots = _shots_made(bridge.calls, previous)
        if not shots:
            raise RuntimeError(f"the director stopped without calling finish or moving a camera: {said[:300]}")
        finished.update(shots=shots, mood=previous.mood if previous else _mood(prompt),
                        summary=previous.summary if previous else "(its cut read from its camera moves)")
    cut = Cut(shots=finished["shots"], mood=finished["mood"], summary=finished["summary"], aspect=aspect,
              calls=[{"name": c["command"], "arguments": c["args"]} for c in bridge.calls])
    run.output(f"live_{label}", run.save_json(f"live/{label}.json", cut.__dict__ | {"duration": cut.duration}))
    run.event("directed", session=label, shots=len(cut.shots), duration=cut.duration, mood=cut.mood,
              summary=cut.summary, calls=len(bridge.calls))
    return cut


async def direct(studio, run: Run, brief: str, profile: BrandProfile, aspect: str = "16:9") -> Cut:
    """The film made in `studio` by Spark from an empty stage, and its cut."""
    return await _session(studio, run, _prompt(brief, profile, aspect), profile, aspect, "direct", max_turns=60)


async def revise(studio, run: Run, cut: Cut, verdict: "Verdict", brief: str, profile: BrandProfile,
                 round_: int = 1) -> Cut:
    """The film in the Studio changed by Spark to answer `verdict`."""
    prompt = f"""The brief: {brief}

{_frame(cut.aspect)}

{_brand(profile)}

{_as_it_is(cut)}

A reviewer watched it and scored it (out of 10; it passes when every score is at least {PASS}):
{json.dumps(verdict.scores.model_dump())}
What's wrong: {json.dumps(verdict.issues)}

Fix what's wrong, in the studio, as you see fit: change the film, don't start a different one unless it
has to be. Preview what you change, then call finish with the film's shots as they are now."""
    return await _session(studio, run, prompt, profile, cut.aspect, f"revise_{round_}", made=True, max_turns=30,
                          previous=cut)


async def adapt(studio, run: Run, cut: Cut, aspect: str, brief: str, profile: BrandProfile) -> Cut:
    """The same film re-shot by Spark for another frame (`aspect`), in the Studio."""
    prompt = f"""The brief: {brief}

{_brand(profile)}

{_as_it_is(cut)} It was made for a {cut.aspect} frame.

Now make the same film for a {aspect} frame. {_frame(aspect)} Keep what it is and how it feels; change
what the new frame needs (cameras and their framing, which take the frame's aspect; titles' size and
place; anything that no longer fits). Preview every shot at the new size, then call finish."""
    return await _session(studio, run, prompt, profile, aspect, f"adapt_{aspect.replace(':', 'x')}", made=True,
                          max_turns=30, previous=cut)


# --- The review ----------------------------------------------------------------------------------

class Scores(BaseModel):
    product: int = Field(ge=1, le=10, description="the product: clear, whole when it should be, true to the brand, the hero")
    light: int = Field(ge=1, le=10, description="light that shapes the product and separates it from the background")
    composition: int = Field(ge=1, le=10, description="framing, balance, the product's size and place in the frame")
    camera: int = Field(ge=1, le=10, description="the moves and the cuts: purposeful, smooth, no jarring jumps")
    titles: int = Field(ge=1, le=10, description="readable, well placed, clear of the product, on brand (10 if none are needed)")
    brand: int = Field(ge=1, le=10, description="the brief and the brand: its colours, mood, and what it must avoid")


class Verdict(BaseModel):
    scores: Scores
    issues: list[str] = Field(description="what's wrong, each concrete: which shot, when, what, and what would fix it; "
                                          "empty if nothing is")

    @property
    def passed(self) -> bool:
        return min(self.scores.model_dump().values()) >= PASS


REVIEW = """You are the creative director reviewing a premium CGI product film before it ships. The first
image shows frames of it: each row is one shot (its start, middle and end), labelled with its time
and what the shot is for.{photo}

The brief: {brief}

{brand}

Score it out of 10 on each count, hard and fair, as you would a real agency's film: 9-10 is
excellent, 7-8 is good, 5-6 has real problems, below 5 fails. Then list what's wrong, concretely."""


async def _frames(studio, cut: Cut, folder: Path) -> tuple[Path, list[Path]]:
    """Frames at each shot's start, middle and end in a sheet, a row a shot,
    labelled; and each shot's middle frame."""
    times = []
    for s in cut.shots:
        edge = min(0.15, (s["end"] - s["start"]) / 4)
        times += [s["start"] + edge, (s["start"] + s["end"]) / 2, s["end"] - edge]
    w, h = frame_size(cut.aspect, PREVIEW_SHORT)
    result = await studio.call("shot.preview", times=times, width=w, height=h, out_dir=str(folder))
    frames = [Path(f["path"]) for f in result["frames"]]
    label = 26
    sheet = Image.new("RGB", (3 * w + 16, len(cut.shots) * (h + label + 8)), (20, 20, 22))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    for row, s in enumerate(cut.shots):
        y = row * (h + label + 8)
        draw.text((6, y + 4), f"shot {row + 1}, {s['start']:.1f}-{s['end']:.1f} s: {s['intent']}"[:160],
                  fill=(235, 235, 235), font=font)
        for col in range(3):
            sheet.paste(Image.open(frames[row * 3 + col]).convert("RGB"), (col * (w + 8), y + label))
    out = folder / "sheet.png"
    sheet.save(out)
    return out, frames[1::3]


async def preview(studio, run: Run, cut: Cut, label: str = "preview") -> Path:
    """Frames of every shot of the film in the Studio (live/<label>/sheet.png);
    each shot's middle frame is the run's preview."""
    sheet, middles = await _frames(studio, cut, run.folder("live", label))
    run.event("preview", frames=[f.relative_to(run.root).as_posix() for f in middles])
    return sheet


async def review(studio, run: Run, cut: Cut, brief: str, profile: BrandProfile, round_: int = 0) -> Verdict:
    """Spark's verdict on the film in the Studio, from frames of every shot
    (live/review_<round>/sheet.png), with the product's photo to compare."""
    sheet = await preview(studio, run, cut, f"review_{round_}")
    photo = next((Path(p) for p in profile.photos if Path(p).exists()), None)
    prompt = REVIEW.format(photo=" The second image is the product's photo." if photo else "", brief=brief,
                           brand=_brand(profile))
    answer = spark.ask(prompt, images=[sheet] + ([photo] if photo else []), schema=Verdict)
    verdict = Verdict.model_validate(answer.data)
    run.save_json(f"live/review_{round_}.json", verdict.model_dump() | {"passed": verdict.passed})
    run.event("live_review", round=round_, passed=verdict.passed, scores=verdict.scores.model_dump(),
              issues=verdict.issues, sheet=sheet.relative_to(run.root).as_posix())
    return verdict


# --- The video -----------------------------------------------------------------------------------

async def render_cut(studio, run: Run, cut: Cut, name: str, short: int = 1080, samples: int = 16) -> Path:
    """The film in the Studio as final/<name>_<w>x<h>.mp4, with music in its
    mood, faded in and out; the run's output video_<w>x<h>. The scene is
    saved first: if the Studio hangs, a new one loads it and renders again."""
    tag = cut.aspect.replace(":", "x")
    width, height = frame_size(cut.aspect, short)
    raw = run.path("final", "raw.mp4")
    frames = round(cut.duration * FPS)
    scene = f"live_{run.root.name}_{tag}"
    await studio.call("scene.save", name=scene)
    run.event("render", frames=frames, width=width, height=height, samples=samples)
    began = time.time()
    args = dict(video=str(raw), end=cut.duration - 1e-3, fps=FPS, width=width, height=height, samples=samples)
    limit = RENDER_SETUP + RENDER_PER_FRAME * frames
    try:
        result = await studio.call("shot.render", _timeout=limit, **args)
    except StudioTimeout as e:   # hung: once more, in a new Studio with the saved scene
        run.event("render_retry", aspect=cut.aspect, error=str(e))
        await studio.restart()
        await studio.call("scene.load", name=scene)
        result = await studio.call("shot.render", _timeout=limit, **args)
    run.event("rendered", frames=result["frames"], seconds=round(time.time() - began, 1))
    sound = music(cut.mood, cut.duration, cut.shots[-1]["start"], run.path("final", "music.wav"))
    run.event("music", mood=cut.mood, file=str(sound.relative_to(run.root)))
    video = finish_video(raw, run.path("final", f"{name}_{tag}.mp4"), fade_in=0.4, fade_out=0.6, audio=sound)
    raw.unlink(missing_ok=True)
    run.output(f"video_{tag}", video)
    return video
