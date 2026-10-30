"""The shot grammar: what the director can ask the Studio for, as a short
text for its prompt (grammar.md). Written from the Studio's own command
descriptions (commands.list) and the Storyboard schema, so it says what the
renderer does, in its words; and checked against both, so a name the
schema allows that the Studio doesn't know (or an argument it lacks) is
caught here, not in a render.

    python -m pipeline.agents.director.grammar      # starts a Studio, checks, writes grammar.md
    text = load()                                   # the grammar for a prompt
"""

import typing
from pathlib import Path

from annotated_types import Ge, Gt, Le, Lt
from pydantic import BaseModel

from pipeline.schemas.storyboard import (Backdrop, CameraMove, Environment, Lighting, Look, Pedestal, ProductMotion,
                                         Shot, Title)

from .styles import STYLES

FILE = Path(__file__).with_name("grammar.md")

# The settings each move reads (the schema's CameraMove has them all).
MOVES = {
    "static": ("holds still", ["fill", "azimuth", "elevation", "fov_degrees"]),
    "orbit": ("circles the product", ["azimuth", "to_azimuth", "elevation", "fill"]),
    "dolly": ("pushes in or pulls out", ["from_fill", "to_fill", "azimuth", "elevation"]),
    "crane": ("rises or drops round it", ["from_elevation", "to_elevation", "azimuth", "fill"]),
    "truck": ("slides sideways past it", ["travel", "azimuth", "elevation", "fill"]),
    "reveal": ("the aim pans onto it from off frame", ["from", "azimuth", "elevation", "fill"]),
    "zoom": ("the lens zooms, the camera stays", ["from_fov", "to_fov", "azimuth", "elevation", "fill"]),
}

# Schema fields whose values must be named in a Studio argument's description.
VOCABULARY = [
    (CameraMove, "move", "camera.move", "move"),
    (CameraMove, "ease", "camera.move", "ease"),
    (CameraMove, "from_", "camera.move", "from"),
    (Lighting, "preset", "lighting.preset", "name"),
    (Title, "font", "text.create", "font"),
    (Environment, "tonemap", "environment.set", "tonemap"),
]

CRAFT = """\
- Open strong: the product is on screen and readable within the first 2 seconds.
- 3 to 6 shots for 15 seconds; no shot under 1.2 s or over 5 s (the style sets the pace).
- Every shot moves differently from the one before (orbit, then dolly, then crane ...): cuts land on motion.
- Keep the side of the product steady across cuts: don't jump more than about 90 degrees of azimuth
  between consecutive shots, unless the cut is meant to surprise.
- Bring the product to life: give one to three shots a `motion` (a drop to open, a turn to bring the label
  round, a float for something light or dreamy). A moving product against a calm camera reads best: pair a
  motion with a static, slow dolly or slow crane, not with a fast orbit. Keep the hero's motion gentle (a
  turn that settles facing front, or none) so the name lands on a still product.
- Low camera (elevation 2-8) feels heroic and premium; high (20-40) feels calm and overseeing.
- fill 0.45 wide, 0.6 medium, 0.9 close; a close-up (0.9+) is for the label or the cap.
- Depth of field (`aperture`) keeps the product sharp and softens what's behind it: use the style's on most
  shots, wider (2-2.8) on close-ups and the hero to set the product apart, 0 on a wide shot whose set should read.
- Glass (a see-through product) shows what's behind it: on a dark set, light it strongly (`intensity` 1.5-2)
  and give it a `glow` (2-3), a warm pool on the wall behind, so the glass lights up in its liquid's colour. A
  lighter backdrop doesn't help: the glass blends into it. The glow is behind the product as seen from the
  front: keep glass shots within about 35 degrees of azimuth 0, or the glass turns dark.
- Glass and metal reflect their surroundings: keep `environment.use_ibl` on.
- Separate the product from the set: the backdrop clearly darker or lighter than the product (a white jar on a
  mid or dark set, a dark product on a lighter one, or a rim-lit dark product on black with strong light).
- Titles must read against what's behind them (the backdrop, and the pedestal for titles low in the frame):
  light on dark, dark on light, a contrast ratio of at least 3.
- The last shot is the hero: static, from the front (azimuth near 0), fill 0.4-0.5 (room for the name), with the brand
  name as a title over it. It lasts at least 2.5 s and the name appears at least 0.4 s into it.
- Titles: the brand name in the brand's font from the brand profile (size 0.06-0.13), an optional tagline
  (0.025-0.035) under it; placed under the product (y 0.8-0.93) so they don't cover it; at most 2 on screen.
- Script is for words in lower or mixed case ("Aurelle", "Skin, simply."), never all capitals; light
  titles on a dark set, dark on a light one.
- Colours (backdrop, pedestal, titles) come from the brand's palette or sit well with it. The brand profile's
  "do not"s are its usual taste: follow them unless the brief asks otherwise, in which case the brief wins.
- The set is sized for the product: a pedestal 1.2-7 times its width and at most 1.5 times its height.
- Start from the style that fits the brief and the brand, then adapt its colours to the palette."""


def _range(info) -> str:
    lo = next((f"{m.ge}" if isinstance(m, Ge) else f">{m.gt}" for m in info.metadata if isinstance(m, (Ge, Gt))), None)
    hi = next((f"{m.le}" if isinstance(m, Le) else f"<{m.lt}" for m in info.metadata if isinstance(m, (Le, Lt))), None)
    choices = _choices(info.annotation)
    if choices:
        return " | ".join(str(c) for c in choices)
    return f"{lo} .. {hi}" if lo is not None and hi is not None else ""


def _choices(annotation) -> list:
    """A Literal's values (inside an Optional too)."""
    if typing.get_origin(annotation) is typing.Literal:
        return list(typing.get_args(annotation))
    for arg in typing.get_args(annotation):
        if typing.get_origin(arg) is typing.Literal:
            return list(typing.get_args(arg))
    return []


def _fields(model: type[BaseModel], skip: tuple = ()) -> list[str]:
    lines = []
    for name, info in model.model_fields.items():
        if name in skip:
            continue
        key = info.alias or name
        notes = [_range(info)]
        if not info.is_required() and info.default is not None:
            notes.append(f"default {info.default}")
        notes = ", ".join(n for n in notes if n)
        lines.append(f"- `{key}`" + (f" ({notes})" if notes else "") +
                     (f": {info.description}" if info.description else ""))
    return lines


def _arg(commands: dict, command: str, arg: str) -> dict | None:
    return next((a for a in commands[command]["args"] if a["name"] == arg), None)


def check(commands: dict) -> list[str]:
    """What's wrong between the schema and the Studio: names the schema allows
    that the Studio's descriptions don't mention, and camera settings the
    Studio has no argument for."""
    problems = []
    for model, field, command, arg in VOCABULARY:
        if command not in commands:
            problems.append(f"the Studio has no {command}")
            continue
        found = _arg(commands, command, arg)
        if found is None:
            problems.append(f"{command} has no argument {arg!r} (for {model.__name__}.{field})")
            continue
        for value in _choices(model.model_fields[field].annotation):
            if value not in found["description"]:
                problems.append(f"{model.__name__}.{field} allows {value!r}, which {command}'s {arg!r} doesn't list")
    for name, info in CameraMove.model_fields.items():
        if _arg(commands, "camera.move", info.alias or name) is None:
            problems.append(f"CameraMove.{name}: camera.move has no argument {info.alias or name!r}")
    for move, (_, settings) in MOVES.items():
        for s in settings:
            if _arg(commands, "camera.move", s) is None:
                problems.append(f"the {move} move reads {s!r}, which camera.move doesn't take")
    if set(MOVES) != set(_choices(CameraMove.model_fields["move"].annotation)):
        problems.append("MOVES and CameraMove.move list different moves")
    return problems


def write(commands: dict) -> str:
    """The grammar as markdown."""
    move = commands["camera.move"]
    out = ["# Shot grammar",
           "",
           "Written by `python -m pipeline.agents.director.grammar` from the Studio's command descriptions and the "
           "Storyboard schema. Don't edit it by hand.",
           "",
           "An ad is shots placed end to end; each shot is one camera move over its duration, so each new shot is a "
           "cut. The product (shape, materials, label) comes from the brand profile: keep it as it is.",
           "",
           "## Camera moves (`shots[].camera`)",
           "",
           f"{move['description']}",
           "",
           "| move | what it does | reads |",
           "|---|---|---|"]
    out += [f"| `{m}` | {what} | {', '.join(f'`{s}`' for s in settings)} |" for m, (what, settings) in MOVES.items()]
    out += ["", "The settings, as the Studio describes them:", ""]
    out += [f"- `{a['name']}`: {a['description']}" for a in move["args"]
            if a["name"] not in ("move", "subject", "duration", "start", "camera", "aspect")]
    out += ["", "## Shots (`shots[]`)", "", *_fields(Shot, skip=("camera", "motion")),
            "", "## Product motion (`shots[].motion`)", "",
            "The product itself moving during a shot, while the camera does its move; it's back at rest at the next "
            "cut. Null (the default) keeps it still.", "", *_fields(ProductMotion),
            "", "## Light (`look.lighting`)", "",
            f"Presets: {_arg(commands, 'lighting.preset', 'name')['description']}.", "", *_fields(Lighting),
            "", "## The set (`look`)", "", *_fields(Look, skip=("environment", "backdrop", "pedestal", "lighting")),
            "", "`look.environment`:", "", *_fields(Environment, skip=("hdri",)),
            "", "`look.backdrop` (a cyclorama: a floor curving up into a wall):", "", *_fields(Backdrop, skip=("texture",)),
            "", "`look.pedestal` (or null: the product stands on the floor):", "", *_fields(Pedestal),
            "", "## Titles (`titles[]`)", "",
            f"Drawn by the Studio over the picture. Fonts: {_arg(commands, 'text.create', 'font')['description']}.",
            "Each fades in at `start` while rising a little and its letters drawing together.", "",
            *_fields(Title),
            "", "## Other animation (`tracks[]`)", "",
            "Keys on any number field of an entity, eased between: for the lights (`light_*`), e.g. one rising or "
            "dimming at a cut. For the product moving, use the shots' `motion`, not a track.",
            "", "## Ad craft", "", CRAFT,
            "", "## Styles", "",
            "Starting points: take the one that fits, then adapt its colours to the brand's palette.", ""]
    for s in STYLES.values():
        t = s.title
        out.append(f"- `{s.name}`: for {s.use_for}. {s.notes[0].upper() + s.notes[1:]}. Lighting `{s.look.lighting.preset}`; "
                   f"titles `{t.font}` {t.color}, tagline `{t.tagline_font}`; shots {s.shot_seconds[0]:g}-"
                   f"{s.shot_seconds[1]:g} s; moves {', '.join(s.moves)}; aperture f/{s.aperture:g}.")
    return "\n".join(out) + "\n"


def load() -> str:
    return FILE.read_text(encoding="utf-8")


async def commands_of(studio) -> dict:
    """The Studio's commands by name: description and arguments."""
    return {c["name"]: c for c in (await studio.call("commands.list"))["commands"]}


if __name__ == "__main__":
    import asyncio
    import sys

    from pipeline.studio import Studio

    async def main() -> int:
        async with Studio() as studio:
            commands = await commands_of(studio)
        problems = check(commands)
        for p in problems:
            print("PROBLEM:", p)
        if problems:
            return 1
        FILE.write_text(write(commands), encoding="utf-8")
        text = load()
        print(f"{FILE}: {len(text.splitlines())} lines, {len(text)} characters (~{len(text) // 4} tokens)")
        return 0

    sys.exit(asyncio.run(main()))
