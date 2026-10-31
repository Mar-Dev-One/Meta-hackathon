"""The stager: Muse Spark stands a 3D model of the product the way the
product stands in its photo, by looking, not by rule. A downloaded model
can come lying down, on its side or upside down, and its proportions alone
can't tell upright from upside down, or its front from its back.

    up, turn = await stage(studio, run, model, photo, height)

The model is rendered standing each of the six ways up (sheet A-F) and
Spark, shown the photo, picks the one standing like the product; then that
one is rendered from eight angles, every 45 degrees (sheet A-H), and Spark
picks the one the photo is taken from (straight on or three-quarters),
which is turned to face the camera."""

from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from pipeline.meta import spark
from pipeline.meta.client import MetaError
from pipeline.runs import Run
from pipeline.schemas import Backdrop, CameraMove, Environment, Lighting, Look, Pedestal, Product, Shot, Storyboard
from pipeline.studio import StudioError, build, models

# What staging can run into: Spark not answering, the Studio refusing the
# model, the model's file not loading (trimesh), a file not written.
FAILURES = (MetaError, StudioError, ValueError, OSError)

LETTERS = "ABCDEFGH"
UP_ANGLES = (0.0, 90.0)   # each way up seen from the front and from its side
SIDES = (0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0)   # the camera's azimuths for the sides sheet:
                                                               # a three-quarter view has its match
TILE = 320                          # each view's height in pixels
ELEVATION = 12                      # a little above: the top and bottom read differently


def _look() -> Look:
    """A plain, evenly lit grey set: the model's shape and markings, nothing else."""
    return Look(environment=Environment(ambient_strength=0.5, bloom=0.0, tonemap="neutral"),
                backdrop=Backdrop(color="#9A9A9E"), pedestal=Pedestal(width=0.05, height=0.02, color="#6A6A6E"),
                lighting=Lighting(preset="high_key"))


async def _views(studio, model: Path, height: float, azimuths: tuple[float, ...], out: Path) -> list[Path]:
    """`model` (normalized) seen from each of `azimuths`, a static shot each."""
    sb = Storyboard(title="stage", brief="-", style="plain", look=_look(),
                    product=Product(model=str(model), height=height),
                    shots=[Shot(id=f"s{i + 1}", intent="-", duration=1,
                                camera=CameraMove(move="static", azimuth=a, elevation=ELEVATION, fill=0.7))
                           for i, a in enumerate(azimuths)])
    try:
        await build(studio, sb)
        result = await studio.call("shot.preview", times=[i + 0.5 for i in range(len(azimuths))],
                                   width=TILE, height=TILE, out_dir=str(out))
    finally:
        models.uninstall(studio, model)   # only for these views: don't leave a copy in the Studio's assets
    return [Path(f["path"]) for f in result["frames"]]


def sheet(views: list[Path | Image.Image], out: Path, across: int | None = None) -> Path:
    """The views (files or pictures, all one size) in rows of `across`
    (default: one row), lettered A, B, ... in their top-left corners."""
    tiles = [v if isinstance(v, Image.Image) else Image.open(v).convert("RGB") for v in views]
    across = across or len(tiles)
    rows = -(-len(tiles) // across)
    gap = 8
    w, h = tiles[0].size
    board = Image.new("RGB", (across * (w + gap) - gap, rows * (h + gap) - gap), (255, 255, 255))
    draw = ImageDraw.Draw(board)
    try:
        font = ImageFont.truetype("arialbd.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    for i, tile in enumerate(tiles):
        x, y = i % across * (w + gap), i // across * (h + gap)
        board.paste(tile, (x, y))
        draw.rectangle((x, y, x + 48, y + 52), fill=(0, 0, 0))
        draw.text((x + 10, y + 4), LETTERS[i], fill=(255, 255, 255), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    return out


async def ups_sheet(studio, source: Path, height: float, folder: Path) -> Path:
    """The model standing each of models.UPS ways up (A-F), each seen from the
    front and, under it, from its side: what it stands on reads whichever
    way it happens to face."""
    views = []
    for up in models.UPS:
        name = up.replace("+", "pos_").replace("-", "neg_")
        stood = models.normalize(source, folder / f"up_{name}.glb", height, up=up)
        front, side = await _views(studio, stood, height, UP_ANGLES, folder / f"up_{name}")
        pair = Image.new("RGB", (TILE, 2 * TILE), (255, 255, 255))
        pair.paste(Image.open(front).convert("RGB"), (0, 0))
        pair.paste(Image.open(side).convert("RGB"), (0, TILE))
        views.append(pair)
    return sheet(views, folder / "ups.png")


async def sides_sheet(studio, source: Path, height: float, up: str, folder: Path) -> Path:
    """The model standing `up`, seen all the way round, every 45 degrees (A the front, C its right, E its
    back, G its left): A-H, in two rows."""
    stood = models.normalize(source, folder / "stood.glb", height, up=up)
    return sheet(await _views(studio, stood, height, SIDES, folder / "sides"), folder / "sides.png", across=4)


# --- Spark's choice ------------------------------------------------------------------------------

class UpChoice(BaseModel):
    reason: str = Field(description="in a sentence: what in the photo and the views decides it (screen, cap, opening, base, text)")
    choice: Literal["A", "B", "C", "D", "E", "F"]


class SideChoice(BaseModel):
    reason: str = Field(description="in a sentence: what in the photo and the views decides it")
    choice: Literal["A", "B", "C", "D", "E", "F", "G", "H"]


SYSTEM = "You are a product photographer staging a 3D model of a product to match its photo exactly."

UP_PROMPT = """The first image is a photo of the product ({category}). The second shows a 3D model of it
standing six different ways (A-F), each on a small grey stand: each column is one way, seen from the
front (top) and from its side (bottom).

Which way stands the model as the product stands in the photo? Find what the product rests on in the
photo (a shoe's sole, a bottle's or a mug's base, a phone's or a watch's lower edge) and what's at its
top (a cap, an opening, a camera notch, a headband, text reading the right way up), and pick the column
where the model rests on that same part with that same part on top: upright, not upside down, not lying
on its side. The model may face any way in these views (the photo's side towards the camera is chosen
next), so judge how it stands, not which side you see."""

SIDE_PROMPT = """The first image is a photo of the product ({category}). The second shows a 3D model of it,
standing upright, from eight angles all the way round, 45 degrees apart (A-H).

Which view shows the product from the same angle as the photo: the same side towards the camera
(front, back or a side: screen or cameras, label or plain back) and the same turn (straight on, or
three-quarters, with the same part nearer the camera)? That view will be the ad's front."""


def _ask(prompt: str, photo: Path, board: Path, schema: type[BaseModel]) -> BaseModel:
    answer = spark.ask(prompt, images=[photo, board], schema=schema, system=SYSTEM)
    return schema.model_validate(answer.data)


async def stage(studio, run: Run | None, source: Path | str, photo: Path | str, height: float,
                category: str = "product", aspect: float | None = None) -> tuple[str, float]:
    """(up, turn) for models.normalize: the way up and the turn Spark sees
    matching the product in `photo`. If the way up can't be chosen (Spark,
    the Studio or the model failing), the guess from the photo's proportions
    (models.orient, `aspect`), or as the file is; if only the side can't,
    that way up, turned as the file is."""
    source, photo = Path(source), Path(photo)
    folder = run.folder("stage") if run else Path(source).parent / "stage"
    try:
        ups = await ups_sheet(studio, source, height, folder)
        first = _ask(UP_PROMPT.format(category=category), photo, ups, UpChoice)
        up = models.UPS[LETTERS.index(first.choice)]
    except FAILURES as e:
        up, turn = models.orient(source, aspect) if aspect else ("+y", 0.0)
        if run:
            run.event("staged", up=up, turn=turn, by="proportions", error=str(e))
        return up, turn
    sheets, side_reason = [ups], None
    try:
        sides = await sides_sheet(studio, source, height, up, folder)
        sheets.append(sides)
        second = _ask(SIDE_PROMPT.format(category=category), photo, sides, SideChoice)
        turn = -SIDES[LETTERS.index(second.choice)] % 360   # the side seen from azimuth a, turned to face azimuth 0
        side_reason = second.reason
    except FAILURES as e:
        turn, side_reason = 0.0, f"(the side couldn't be chosen, so as the file is: {e})"
    if run:
        run.event("staged", up=up, turn=turn, by="spark", up_reason=first.reason, side_reason=side_reason,
                  sheets=[p.relative_to(run.root).as_posix() for p in sheets])
    return up, turn
