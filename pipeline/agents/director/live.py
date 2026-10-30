"""The live director: Muse Spark makes the ad in the Studio itself, with every
command the Studio has (pipeline.studio.tools), not by filling in a
storyboard. It decides the set, the props, the light, the cameras, the
animation and the titles, looks at its previews, changes what it doesn't
like, and declares its cut when it's done.

    cut = await direct(studio, run, brief, profile, aspect="16:9")
    cut.shots          # [{"start", "end", "intent"}], back to back from 0
    cut.duration, cut.mood

Two tools sit beside the commands: make_product (the brand's own product,
the traced shape or the dressed 3D model, which is too much data to type
into product.create) and finish (the cut: the shots, the music's mood).
The product is always the entity "product", which the critic measures.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.runs import Run
from pipeline.schemas import BrandProfile
from pipeline.studio import PRODUCT, StudioError
from pipeline.studio.build import ASPECTS, create_product, place_product_model
from pipeline.studio.tools import Bridge

MOODS = ("dark", "calm", "energetic", "warm")   # the music (pipeline.encode.music)
PREVIEW_SHORT = 360                             # previews' shorter side in pixels
MAKERS = ("product.create", "place_model", "entity.create", "backdrop.create", "entity.update")   # name an entity


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
- history.undo undoes your last change; batch runs several commands as one.

Make it look like a real, expensive product film: considered composition, light that shapes the
product and separates it from the background, purposeful camera movement, nothing cheap or
cluttered. Respect the brand: its colours, its mood, what it must avoid.

When the film is done, call finish with its shots (back to back from 0, each with what it's for),
the music's mood and a sentence about the film. Then answer in one sentence."""


def _prompt(brief: str, profile: BrandProfile, aspect: str) -> str:
    w, h = ((round(PREVIEW_SHORT * ASPECTS[aspect]), PREVIEW_SHORT) if ASPECTS[aspect] >= 1
            else (PREVIEW_SHORT, round(PREVIEW_SHORT / ASPECTS[aspect])))
    brand = profile.model_dump(include={"brand", "product_name", "category", "height", "palette", "materials",
                                        "typography", "mood", "do_not"}, exclude_none=True)
    shape = "a 3D model of it" if profile.model else "its shape traced from its photo, with its label"
    return f"""The brief: {brief}

The frame is {aspect} (aspect {ASPECTS[aspect]:.4f}); preview at {w}x{h}.

The brand, as read from the product's photo (the product is {shape}; make_product puts it in the
scene):
{json.dumps(brand, indent=1)}

The stage is empty. Make the film."""


def _tools(studio, profile: BrandProfile, finished: dict) -> dict:
    async def make_product(args: dict) -> dict:
        product = profile.product()
        top = float((args.get("position") or [0, 0, 0])[1])
        if any(e.get("name") == PRODUCT for e in (await studio.call("scene.describe")).get("entities", [])):
            await studio.call("entity.destroy", entity=PRODUCT)
        if product.model:
            await place_product_model(studio, product, top)
        else:
            await create_product(studio, product, top)
        position = args.get("position") or [0, 0, 0]
        if args.get("on_top_of"):
            await studio.call("entity.place", entity=PRODUCT, relative_to={"entity": args["on_top_of"], "side": "on_top"})
        elif position[0] or position[2]:
            await studio.call("entity.place", entity=PRODUCT, position=position)
        finished["made"] = True
        return await studio.call("entity.get", entity=PRODUCT)

    async def finish(args: dict) -> dict:
        shots = sorted(args.get("shots") or [], key=lambda s: s.get("start", 0))
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


def _refuse(command: str, args: dict) -> str | None:
    """Turns down any command but make_product making an entity called "product"."""
    if command in MAKERS and args.get("name") == PRODUCT:
        return (f"{command} can't make the entity \"{PRODUCT}\": the brand's product comes only from make_product "
                "(its real shape and label, or its real model). Give other objects other names.")
    return None


async def direct(studio, run: Run, brief: str, profile: BrandProfile, aspect: str = "16:9",
                 max_turns: int = 60) -> Cut:
    """The film made in `studio` by Spark, and its cut (live.json in the run;
    its previews in live/previews/, every command in the run's log)."""
    finished: dict = {}

    def logged(command: str, args: dict, result) -> None:
        error = result.get("error") if isinstance(result, dict) else None
        run.event("tool", command=command, args=args, error=error)

    bridge = await Bridge.open(studio, on_call=logged, extra=_tools(studio, profile, finished),
                               previews=run.folder("live", "previews"), refuse=_refuse)
    result = await bridge.run(_prompt(brief, profile, aspect), system=SYSTEM, max_turns=max_turns)
    if "shots" not in finished:
        raise RuntimeError(f"the director stopped without calling finish: {result.text[:300]}")
    cut = Cut(shots=finished["shots"], mood=finished["mood"], summary=finished["summary"], aspect=aspect,
              calls=[{k: c[k] for k in ("name", "arguments")} for c in result.calls])
    run.output("live", run.save_json("live.json", cut.__dict__ | {"duration": cut.duration}))
    run.event("directed", shots=len(cut.shots), duration=cut.duration, mood=cut.mood, summary=cut.summary,
              calls=len(result.calls))
    return cut
