"""The scout: from the product's photo alone, whether the product needs a 3D
model, and which one. Round products (bottles, jars, cans) are traced from
the photo and keep their real label; any other shape (a phone, a shoe, a
box) is looked for online (pipeline.catalog) and Muse Spark picks the
closest model by looking: first its top few from the catalogues'
thumbnails, then, those downloaded and rendered alike in the Studio (a
thumbnail can be a scene, a beauty render, a different model's picture),
the one whose render is closest.

    need = shape(photo, category)        # Shape: round, or the words to search for
    ranked, answer, board = pick(photo, need.queries, folder, category)   # catalog.Candidates, best first
    model, credit = await scout(run, photo, category, studio=studio)   # logged in the run: the model's .glb, or None
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
from pipeline.studio import StudioError, models

from .stager import LETTERS, TILE as VIEW, _views, sheet as lettered

CANDIDATES = 12   # thumbnails on the sheet Spark picks from, at most (4 x 3)
FINALISTS = 3     # of them downloaded and rendered, for the pick by render
AUDITION = ((30.0, 12.0), (120.0, 12.0), (30.0, 60.0))   # each finalist's views: (azimuth, elevation)
FACES = (200, 1_000_000)   # a model's faces: fewer is too crude to pass for the product, more too heavy to render
PER_SEARCH = 4    # from each source for each search
TILE = 256

SYSTEM = "You are a 3D artist preparing a product for a CGI ad."


class NoModel(Exception):
    """The product isn't round and no model can stand in for it: traced
    from the photo it would be a turned blob (a drone as a mushroom), so the
    ad stops here and asks for a model instead."""

    def __init__(self, category: str, why: str):
        super().__init__(f"no 3D model fits this {category}: {why}. Give a model of it (.glb, the command line's --model) to make its ad")


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
    reason: str = Field(description="in a sentence: how the chosen models' shapes match the product's, or why none does")
    branded: list[int] = Field(default_factory=list,
                               description="the numbers of the models carrying a real brand: a logo, a brand name or "
                                           "lettering on them, or in their title, or a specific real branded product "
                                           "(a named car, a famous camera)")
    choices: list[int] = Field(max_length=FINALISTS,
                               description=f"the numbers of the closest models, up to {FINALISTS}, the closest first, "
                                           "none of them branded; empty if none is the same kind of product")


PICK_PROMPT = """The first image is a photo of a product ({category}). The second shows 3D models found online,
numbered 1-{n}. One will stand in for the product in a CGI ad: it gets the product's colours and
materials, so only its shape matters, not its colour, texture or background.

Which models have the closest shape to the product: the same kind of product, the same proportions
and the same features (a camera bump, a cap, buttons, a handle)? Prefer a single clean product over
a scene, a set of several objects or a rough, low-detail model. Give up to {finalists}, the closest
first (they'll be looked at more closely); none if none is the same kind of product.

An ad never shows another company's brand. List as branded every model with a real brand on it (a
logo, a brand name, any lettering), in its title, or that is a specific real branded product (a named
car model, a famous camera): never choose those, however close.

Their titles:
{titles}"""


class Final(BaseModel):
    reason: str = Field(description="in a sentence: what in the renders decides it (shape, features, detail, defects)")
    branded: list[str] = Field(default_factory=list,
                               description="the letters of the models carrying a real brand's logo, name or lettering")
    choice: str = Field(description="the letter of the model to use, not a branded one")


FINAL_PROMPT = """The first image is a photo of a product ({category}). The second shows {n} 3D models of
it (A-{last}), downloaded for a CGI ad, each column one model rendered in the same plain grey studio
from three angles (two from the side, one from above). A model may lie on its side or upside down:
it will be stood up the way the product stands, so don't judge how it's lying. It will also be
repainted in the product's colours, so don't judge its colours.

Which model will stand in for the product best? The same kind of product with the same shape and
proportions, the same features (a camera bump, a cap, buttons, a handle, a sole's tread); then the
cleanest: one whole object, finely detailed, with nothing broken or missing, no holes or spikes, and
nothing else with it (no floor, stand, box, hand or second product).

An ad never shows another company's brand: list as branded every model with a real brand's logo, name
or lettering on it (repainting keeps them), and never choose one."""


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
         ) -> tuple[list[Candidate], Pick | None, Path | None]:
    """The models Spark sees closest to the product in `photo` from their
    thumbnails, of those found for `queries`, the closest first (up to
    FINALISTS): (candidates, Spark's answer, the sheet); no candidates if
    nothing was found or none is the same kind of product."""
    found = candidates(queries)
    if not found:
        return [], None, None
    board, shown = sheet(found, folder / "candidates.png")
    titles = "\n".join(f"{i}. {c.name}" for i, c in enumerate(shown, 1))
    answer = spark.ask(PICK_PROMPT.format(category=category, n=len(shown), finalists=FINALISTS, titles=titles),
                       images=[photo, board], schema=Pick, system=SYSTEM)
    chosen = Pick.model_validate(answer.data)
    numbers = list(dict.fromkeys(n for n in chosen.choices if 1 <= n <= len(shown) and n not in chosen.branded))
    return [shown[n - 1] for n in numbers], chosen, board


async def audition(studio, photo: Path | str, finalists: list[tuple[Candidate, Path]], folder: Path,
                   category: str = "product") -> tuple[int | None, Final, Path]:
    """Which of `finalists` ((candidate, its .glb)) Spark sees standing in
    best for the product in `photo`, rendered alike: (its index, Spark's
    answer, the sheet); a branded one never (the next unbranded instead,
    None if all are). They're shown in an order of their own (by their
    keys), not best thumbnail first: the first column isn't a hint."""
    order = sorted(range(len(finalists)), key=lambda i: hashlib.sha1(finalists[i][0].key.encode()).hexdigest())
    columns = []
    for i in order:
        glb = finalists[i][1]
        size = models.normalize(glb, folder / f"finalist_{i + 1}.glb", 0.15)
        views = await _views(studio, size, 0.15, tuple(a for a, _ in AUDITION), folder / f"finalist_{i + 1}",
                             elevations=tuple(e for _, e in AUDITION))
        column = Image.new("RGB", (VIEW, VIEW * len(views)), (255, 255, 255))
        for k, view in enumerate(views):
            column.paste(Image.open(view).convert("RGB"), (0, VIEW * k))
        columns.append(column)
    board = lettered(columns, folder / "finalists.png")
    answer = spark.ask(FINAL_PROMPT.format(category=category, n=len(finalists), last=LETTERS[len(finalists) - 1]),
                       images=[photo, board], schema=Final, system=SYSTEM)
    final = Final.model_validate(answer.data)
    letter = final.choice.strip().upper()[:1]
    if letter not in LETTERS[:len(finalists)]:
        raise ValueError(f"no model {final.choice!r} among A-{LETTERS[len(finalists) - 1]}")
    branded = {b.strip().upper()[:1] for b in final.branded}
    if letter in branded:   # its pick is branded after all: the closest unbranded, by the thumbnails' ranking
        letter = next((LETTERS[order.index(i)] for i in range(len(finalists))
                       if LETTERS[order.index(i)] not in branded), None)
    return order[LETTERS.index(letter)] if letter else None, final, board


async def scout(run: Run, photo: Path | str, category: str = "product",
                studio=None) -> tuple[Path | None, dict | None]:
    """The model for the product in `photo`, downloaded, and its credit; or
    (None, None) when the product is round, or Spark can't say (it's traced
    from the photo then). One that isn't round with no model to stand in for
    it (none found, none fits, every one branded, none would download) is
    NoModel: traced, it would be a blob. With a `studio`, Spark's top
    thumbnails are downloaded and rendered, and it picks by the renders
    (audition); if that fails, or without one, its closest thumbnail wins.
    Each step is logged in `run` (scouted, model_pick, model_download,
    model_audition; scout_failed), the sheets saved in its stage/ folder."""
    need = None
    try:
        need = shape(photo, category)
        run.event("scouted", round=need.round, reason=need.reason, queries=need.queries)
        if need.round:
            return None, None
        folder = run.folder("stage")
        ranked, answer, board = pick(photo, need.queries, folder, category)
        run.event("model_pick", name=ranked[0].name if ranked else None, source=ranked[0].source if ranked else None,
                  finalists=[c.name for c in ranked], reason=answer.reason if answer else "nothing found",
                  branded=answer.branded if answer else [],
                  sheet=board.relative_to(run.root).as_posix() if board else None)
        finalists = []
        for found in ranked if studio else ranked[:1]:
            run.event("model_download", source=found.source, name=found.name)
            try:
                glb = catalog.download(found)
                faces = models.faces(glb)
                if not FACES[0] <= faces <= FACES[1]:
                    run.event("model_rejected", name=found.name, faces=faces,
                              reason=f"{faces} faces: {'too crude' if faces < FACES[0] else 'too heavy to render'}")
                    continue
                finalists.append((found, glb))
            except (CatalogError, OSError, ValueError) as e:   # one that won't download or load: the others still can
                run.event("scout_failed", error=f"{found.name}: {e}")
    except (MetaError, CatalogError, ValueError, OSError) as e:   # OSError: requests' network errors too
        run.event("scout_failed", error=str(e))
        if need is None:   # not even its shape known: traced, as a round one would be
            return None, None
        raise NoModel(category, f"the search failed ({e})") from e
    if not finalists:
        raise NoModel(category, "none of the close models would download or render" if ranked
                      else answer.reason if answer else "the catalogues have nothing for it")
    chosen = 0
    if len(finalists) > 1:
        try:
            picked, final, board = await audition(studio, photo, finalists, folder, category)
            run.event("model_audition", name=finalists[picked][0].name if picked is not None else None,
                      source=finalists[picked][0].source if picked is not None else None,
                      reason=final.reason, branded=final.branded, sheet=board.relative_to(run.root).as_posix(),
                      finalists=[c.name for c, _ in finalists], thumbnail_pick=finalists[0][0].name)
            if picked is None:   # every one carries a brand
                raise NoModel(category, "every model close enough carries another company's brand")
            chosen = picked
        except (MetaError, StudioError, ValueError, OSError) as e:
            run.event("model_audition", name=finalists[0][0].name, error=str(e))
    found, glb = finalists[chosen]
    return glb, found.to_json()
