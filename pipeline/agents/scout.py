"""The scout: from the product's photo alone, whether the product needs a 3D
model, and which one. Round products (bottles, jars, cans) are traced from
the photo and keep their real label; any other shape (a phone, a shoe, a
box) is looked for online (pipeline.catalog) and Muse Spark picks the
closest model by looking at the candidates.

    need = shape(photo, category)        # Shape: round, or the words to search for
    found, answer, board = pick(photo, need.queries, folder, category)   # a catalog.Candidate, or None
    model, credit = scout(run, photo, category)   # both, logged in the run: the model's .glb, or None
"""

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic import BaseModel, Field

from pipeline import catalog
from pipeline.catalog.common import CACHE, CatalogError, Candidate, fetch
from pipeline.meta import spark
from pipeline.meta.client import MetaError
from pipeline.runs import Run

CANDIDATES = 12   # thumbnails on the sheet Spark picks from, at most (4 x 3)
PER_SEARCH = 4    # from each source for each search
TILE = 256

SYSTEM = "You are a 3D artist preparing a product for a CGI ad."


class Shape(BaseModel):
    reason: str = Field(description="in a sentence: the product's shape, seen from above and from the side")
    round: bool = Field(description="true if the product is round seen from above, the same all the way round "
                                    "(a bottle, a jar, a can, a tube, a candle): it's made by spinning its outline")
    queries: list[str] = Field(max_length=3,
                               description="not round: 2-3 short searches for a 3D model of it, the most "
                                           "specific first ('iphone pro', 'smartphone', 'phone'); empty if round")


SHAPE_PROMPT = """This is a photo of a product ({category}). For the ad it becomes a 3D model.

If it's round seen from above (a bottle, a jar, a can, a tube: the same all the way round), it's
made by spinning the outline in the photo, and keeps its real label. Anything else (a phone, a
shoe, a box, headphones, a watch, a square bottle) needs a 3D model found online: say what to search
for, in 2-3 short searches of 1-3 words each, the most specific first (the kind of product, a
well-known model name if it's clearly one, never the brand's own name alone).

A photo straight from the front doesn't show depth: a bottle, jar or can is round unless the photo
shows it isn't (flat side faces at an angle, sharp vertical corners, a box-like top). When unsure,
say round: the traced shape keeps the product's real label, a model found online doesn't."""


def shape(photo: Path | str, category: str = "product") -> Shape:
    """Round (traced from the photo) or not (with searches for a model)."""
    answer = spark.ask(SHAPE_PROMPT.format(category=category), images=[photo], schema=Shape, system=SYSTEM)
    need = Shape.model_validate(answer.data)
    if not need.round and not need.queries:
        raise ValueError(f"Spark found the product isn't round but gave nothing to search for: {need.reason}")
    return need if not need.round else need.model_copy(update={"queries": []})


# --- The pick --------------------------------------------------------------------------------------

class Pick(BaseModel):
    reason: str = Field(description="in a sentence: how the chosen model's shape matches the product's, or why none does")
    choice: int = Field(ge=0, le=CANDIDATES, description="the number of the closest model; 0 if none is the same kind of product")


PICK_PROMPT = """The first image is a photo of a product ({category}). The second shows 3D models found online,
numbered 1-{n}. One will stand in for the product in a CGI ad: it gets the product's colours and
materials, so only its shape matters, not its colour, texture or background.

Which model has the closest shape to the product: the same kind of product, the same proportions
and the same features (a camera bump, a cap, buttons, a handle)? Prefer a single clean product over
a scene, a set of several objects or a rough, low-detail model. Answer 0 if none is the same kind
of product."""


def candidates(queries: list[str]) -> list[Candidate]:
    """Models for `queries` from every catalogue, the most specific search's
    first, each model once, without the ones that can't be downloaded."""
    found, seen = [], set()
    for query in queries:
        for c in catalog.search(query, limit=PER_SEARCH):
            if c.key not in seen and not c.needs_token and c.thumbnail:
                seen.add(c.key)
                found.append(c)
    return found[:CANDIDATES]


def _thumbnail(c: Candidate) -> Image.Image | None:
    path = CACHE / "thumbnails" / (hashlib.sha1(c.key.encode()).hexdigest()[:16] + ".img")
    try:
        if not path.exists():
            fetch(c.thumbnail, path)
        return ImageOps.fit(Image.open(path).convert("RGB"), (TILE, TILE))
    except (CatalogError, OSError):
        return None


def sheet(found: list[Candidate], out: Path) -> tuple[Path, list[Candidate]]:
    """The candidates' thumbnails in a grid of four across, numbered from 1,
    and the candidates in that order (ones whose thumbnail won't load left out)."""
    tiles = [(c, t) for c in found if (t := _thumbnail(c)) is not None]
    gap, across = 8, 4
    rows = max(1, -(-len(tiles) // across))
    board = Image.new("RGB", (across * (TILE + gap) - gap, rows * (TILE + gap) - gap), (255, 255, 255))
    draw = ImageDraw.Draw(board)
    try:
        font = ImageFont.truetype("arialbd.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    for i, (_, tile) in enumerate(tiles):
        x, y = i % across * (TILE + gap), i // across * (TILE + gap)
        board.paste(tile, (x, y))
        draw.rectangle((x, y, x + 56, y + 48), fill=(0, 0, 0))
        draw.text((x + 8, y + 4), str(i + 1), fill=(255, 255, 255), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    return out, [c for c, _ in tiles]


def pick(photo: Path | str, queries: list[str], folder: Path, category: str = "product"
         ) -> tuple[Candidate, Pick, Path] | tuple[None, Pick | None, Path | None]:
    """The model Spark sees closest to the product in `photo`, of those
    found for `queries`: (candidate, Spark's answer, the sheet), or None for
    the candidate if nothing was found or none is the same kind of product."""
    found = candidates(queries)
    if not found:
        return None, None, None
    board, shown = sheet(found, folder / "candidates.png")
    answer = spark.ask(PICK_PROMPT.format(category=category, n=len(shown)), images=[photo, board], schema=Pick,
                       system=SYSTEM)
    chosen = Pick.model_validate(answer.data)
    if not 1 <= chosen.choice <= len(shown):
        return None, chosen, board
    return shown[chosen.choice - 1], chosen, board


def scout(run: Run, photo: Path | str, category: str = "product") -> tuple[Path | None, dict | None]:
    """The model for the product in `photo`, downloaded, and its credit; or
    (None, None) when the product is round, or no model fits, or the search
    fails: then it's traced from the photo. Each step is logged in `run`
    (scouted, model_pick, model_download; scout_failed), the sheet saved in
    its stage/ folder."""
    try:
        need = shape(photo, category)
        run.event("scouted", round=need.round, reason=need.reason, queries=need.queries)
        if need.round:
            return None, None
        found, answer, board = pick(photo, need.queries, run.folder("stage"), category)
        run.event("model_pick", name=found.name if found else None, source=found.source if found else None,
                  reason=answer.reason if answer else "nothing found",
                  sheet=board.relative_to(run.root).as_posix() if board else None)
        if not found:
            return None, None
        run.event("model_download", source=found.source, name=found.name)
        return catalog.download(found), found.to_json()
    except (MetaError, CatalogError, ValueError, OSError) as e:   # OSError: requests' network errors too
        run.event("scout_failed", error=str(e))
        return None, None
