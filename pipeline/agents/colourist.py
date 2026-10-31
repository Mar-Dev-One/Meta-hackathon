"""The colourist: a downloaded model in the product's own colours, chosen by
Muse Spark looking, not by rule. The model comes in its modeller's colours
(a grey sneaker for a white and coral one); recolour.versions() repaints it
in the photo's colours, pairing its regions with them by size and by
lightness, and either can be wrong (a sole and an upper swapped), so Spark
sees the photo next to the model as it is (A) and each version (B, C),
front and three-quarters, and keeps the closest.

    by = await colour(studio, run, run.path("product.glb"), photo, colours, height)   # "lightness", or None
"""

import shutil
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from pipeline.meta import spark
from pipeline.runs import Run
from pipeline.studio import models, recolour

from .stager import FAILURES, LETTERS, TILE, _views, sheet

ANGLES = (0.0, 45.0)   # each version seen from the front and three-quarters

SYSTEM = "You are a product photographer checking a 3D model of a product against its photo."

PROMPT = """The first image is a photo of the product ({category}). The second shows a 3D model of it in
{n} colourings (A-{last}), each column one colouring, seen from the front (top) and three-quarters
(bottom). A is the model as it was made; the others are repainted in the photo's colours.

Which colouring matches the product in the photo best? Judge the parts by size, biggest first:
1. The main part, most of what you see (a controller's or a mug's body, a shoe's upper, a watch's
   strap, headphones' cups and band): is it the photo's colour (black stays black, white stays white,
   an orange body where the photo's is black is wrong)? This matters most.
2. Then the next biggest (a sole, a dial, a handle, cushions), then small details (buttons, stick
   tops, laces, rims), which matter least: a colouring with the right main part and a few small
   parts off beats one with the wrong main part.
The light differs, so judge which part is which colour, not exact brightness. A is the model as it
was made: pick it when the repaintings put colours on the wrong parts (a sole and an upper swapped,
a dial taking the strap's colour)."""


class ColourChoice(BaseModel):
    reason: str = Field(description="in a sentence: the main part's colour, then the others', in the photo and in the choice")
    choice: Literal["A", "B", "C"]


async def colour(studio, run: Run | None, model: Path | str, photo: Path | str,
                 colours: list[tuple[str, float]], height: float, category: str = "product") -> str | None:
    """`model` (fitted, in place) in whichever colouring Spark sees closest
    to `photo`: how its regions were paired with `colours` ("size",
    "lightness"), or None if it's kept as it was (Spark choosing A, or
    anything failing)."""
    model, photo = Path(model), Path(photo)
    folder = run.folder("colour") if run else model.parent / "colour"
    try:
        made = recolour.versions(model, colours, folder)
        original = shutil.copy(model, folder / f"{model.stem}_as_made.glb")
        candidates = [("as made", Path(original)), *made.items()]
        columns = []
        for name, glb in candidates:
            front, side = await _views(studio, glb, height, ANGLES, folder / name.replace(" ", "_"))
            pair = Image.new("RGB", (TILE, 2 * TILE), (255, 255, 255))
            pair.paste(Image.open(front).convert("RGB"), (0, 0))
            pair.paste(Image.open(side).convert("RGB"), (0, TILE))
            columns.append(pair)
        board = sheet(columns, folder / "colourings.png")
        answer = spark.ask(PROMPT.format(category=category, n=len(candidates), last=LETTERS[len(candidates) - 1]),
                           images=[photo, board], schema=ColourChoice, system=SYSTEM)
        choice = ColourChoice.model_validate(answer.data)
        index = LETTERS.index(choice.choice)
        if index >= len(candidates):
            raise ValueError(f"no colouring {choice.choice}")
    except FAILURES as e:
        if run:
            run.event("recoloured", by=None, error=str(e))
        return None
    by = None if index == 0 else candidates[index][0]
    if by:
        shutil.copy(candidates[index][1], model)
        models.opaque(model)   # the repainted file is written afresh: solid again
    if run:
        run.event("recoloured", by=by, reason=choice.reason, colours=[h for h, _ in colours],
                  sheet=board.relative_to(run.root).as_posix())
    return by
