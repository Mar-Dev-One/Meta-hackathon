"""Revision: the director changes a storyboard to answer a written fix (the
critic's, or a person's), with Muse Spark calling tools that edit it.

    sb2, changes = await revise(sb, "s3 should end in a close-up on the label", profile, studio=studio, run=run)
    changes      # ["shots[2].camera.to_fill: 0.9 -> 1.25", ...]

The tools edit the storyboard, not the Studio: every change stays in the
storyboard, which is rebuilt as before, so a revision can be replayed,
compared and undone. Each edit is checked against the schema as it's made
(a bad one isn't applied, and Spark is told why); the craft rules are
checked when Spark is done, and what's still wrong goes back for another
round.
"""

import copy
import json

from pydantic import ValidationError

from pipeline.meta import spark
from pipeline.schemas import BrandProfile, Storyboard

from . import grammar
from .write import DirectorError, _errors, _profile_text, problems, title_problems

CHANGES = {"type": "object", "additionalProperties": True}

TOOLS = [
    {"type": "function", "name": "edit_shot",
     "description": "Changes a shot: any of duration, intent, and camera settings (only the ones given change; "
                    "e.g. {\"duration\": 3, \"camera\": {\"to_fill\": 1.2}}). A new camera move replaces the old "
                    "one's settings: give every setting it needs.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "changes": CHANGES},
                    "required": ["id", "changes"]}},
    {"type": "function", "name": "add_shot",
     "description": "Adds a shot after the one with id `after` (\"\" for first): {id, intent, duration, camera}.",
     "parameters": {"type": "object", "properties": {"after": {"type": "string"}, "shot": CHANGES},
                    "required": ["after", "shot"]}},
    {"type": "function", "name": "remove_shot", "description": "Removes a shot.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"type": "function", "name": "edit_look",
     "description": "Changes the set and light: any of environment, background, backdrop, pedestal, lighting, "
                    "each with only the settings to change (e.g. {\"pedestal\": {\"height\": 0.04}, \"lighting\": "
                    "{\"intensity\": 0.8}}); \"pedestal\": null removes the pedestal.",
     "parameters": {"type": "object", "properties": {"changes": CHANGES}, "required": ["changes"]}},
    {"type": "function", "name": "edit_title",
     "description": "Changes a title (by its index, from 0): any of text, font, size, y, color, tracking, start, fade.",
     "parameters": {"type": "object", "properties": {"index": {"type": "integer"}, "changes": CHANGES},
                    "required": ["index", "changes"]}},
    {"type": "function", "name": "add_title",
     "description": "Adds a title: {text, font, size, y, color, tracking, start, fade}.",
     "parameters": {"type": "object", "properties": {"title": CHANGES}, "required": ["title"]}},
    {"type": "function", "name": "remove_title", "description": "Removes a title (by its index, from 0).",
     "parameters": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}},
]

SYSTEM = ("You are the director of a studio that makes short 3D product adverts, revising one of your ads. You "
          "change what the fix asks for and what that change needs, nothing else, using the tools; each tool "
          "edits the storyboard and says whether the edit was valid. When it's done, answer in one sentence "
          "saying what you changed, without calling a tool.")

PROMPT = """# The fix to make

{fix}

# The storyboard now

{storyboard}

# The brand profile

{profile}

{grammar}"""


def _merge(base: dict, changes: dict) -> dict:
    """`base` with `changes` merged in, dicts recursively; None removes a key."""
    out = copy.deepcopy(base)
    for key, value in changes.items():
        if value is None:
            out[key] = None
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def diff(a, b, path: str = "") -> list[str]:
    """What changed from `a` to `b` (plain data), one line per value."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [line for k in dict.fromkeys([*a, *b])
                for line in diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [line for i, (x, y) in enumerate(zip(a, b)) for line in diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {json.dumps(a)} -> {json.dumps(b)}"]


class _Editor:
    """The storyboard being revised, as plain data, and the tools' handler."""

    def __init__(self, sb: Storyboard, profile: BrandProfile):
        self.data = sb.model_dump(by_alias=True, exclude_none=True)
        self.data["product"] = sb.product.model_dump(by_alias=True)
        self.profile, self.seconds = profile, sb.duration

    def storyboard(self) -> Storyboard:
        return Storyboard.model_validate(self.data)

    def _shot(self, shot_id: str) -> int:
        ids = [s["id"] for s in self.data["shots"]]
        if shot_id not in ids:
            raise KeyError(f"no shot {shot_id!r}; the shots are {ids}")
        return ids.index(shot_id)

    def _try(self, data: dict) -> dict:
        """Keeps `data` if it's a valid storyboard; says what's still to
        fix (the craft rules) either way."""
        try:
            sb = Storyboard.model_validate(data)
        except ValidationError as e:
            return {"applied": False, "errors": _errors(e)}
        self.data = data
        left = problems(sb, self.profile, self.seconds)
        return {"applied": True, "length": sb.duration, **({"still_to_fix": left} if left else {})}

    def handle(self, name: str, args: dict) -> dict:
        data = copy.deepcopy(self.data)
        if name == "edit_shot":
            i = self._shot(args["id"])
            changes = dict(args["changes"])
            camera = changes.pop("camera", None)
            if camera and camera.get("move") not in (None, data["shots"][i]["camera"]["move"]):
                data["shots"][i]["camera"] = {}   # a new move: its own settings, not the old one's
            data["shots"][i] = _merge(data["shots"][i], changes)
            if camera:
                data["shots"][i]["camera"] = _merge(data["shots"][i]["camera"], camera)
        elif name == "add_shot":
            at = 0 if not args["after"] else self._shot(args["after"]) + 1
            data["shots"].insert(at, args["shot"])
        elif name == "remove_shot":
            del data["shots"][self._shot(args["id"])]
        elif name == "edit_look":
            data["look"] = _merge(data["look"], args["changes"])
        elif name == "edit_title":
            data["titles"][args["index"]] = _merge(data["titles"][args["index"]], args["changes"])
        elif name == "add_title":
            data["titles"].append(args["title"])
        elif name == "remove_title":
            del data["titles"][args["index"]]
        else:
            return {"applied": False, "errors": [f"no tool {name!r}"]}
        return self._try(data)


async def revise(sb: Storyboard, fix: str, profile: BrandProfile, *, studio=None, run=None,
                 rounds: int = 3) -> tuple[Storyboard, list[str]]:
    """The storyboard changed to answer `fix`, and what changed. Its length
    stays the same. DirectorError if it can't be made valid in `rounds`."""
    before = sb.model_dump(by_alias=True, exclude_none=True)
    editor = _Editor(sb, profile)
    prompt = fix
    for round_ in range(1, rounds + 1):
        text = PROMPT.format(fix=prompt, storyboard=json.dumps(editor.data | {"product": "(from the brand profile)"},
                                                               indent=1),
                             profile=_profile_text(profile), grammar=grammar.load())
        result = spark.run_tools(text, tools=TOOLS, handle=editor.handle, system=SYSTEM, max_turns=10)
        revised = editor.storyboard()
        found = problems(revised, profile, editor.seconds) + (await title_problems(studio, revised) if studio else [])
        if run:
            run.event("revision", round=round_, calls=[{"name": c["name"], "arguments": c["arguments"],
                                                        "applied": c["result"].get("applied")} for c in result.calls],
                      summary=result.text, problems=found)
        if not found:
            changes = diff(before, revised.model_dump(by_alias=True, exclude_none=True))
            if run:
                run.save_json("storyboard.json", revised)
                run.event("revised", changes=changes)
            return revised, changes
        prompt = (f"{fix}\n\nYou revised it; these problems are left, fix them too (keep what answers the fix):\n" +
                  "\n".join(f"- {p}" for p in found))
    raise DirectorError(f"the revision still has problems after {rounds} rounds: " + "; ".join(found))
