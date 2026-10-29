"""The stager: Muse Spark stands a 3D model of the product the way the
product stands in its photo, by looking, not by rule. A downloaded model
can come lying down, on its side or upside down, and its proportions alone
can't tell upright from upside down, or its front from its back.

    up, turn = await stage(studio, run, model, photo, height)

The model is rendered standing each of the six ways up (sheet A-F) and
Spark, shown the photo, picks the one standing like the product; then that
one is rendered from four sides (sheet A-D) and Spark picks the side the
photo shows, which is turned to face the camera."""

from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field

from pipeline.meta import spark
from pipeline.meta.client import MetaError
from pipeline.runs import Run
from pipeline.schemas import Backdrop, CameraMove, Environment, Lighting, Look, Pedestal, Product, Shot, Storyboard
from pipeline.studio import build, models

LETTERS = "ABCDEF"
SIDES = (0.0, 90.0, 180.0, 270.0)   # the camera's azimuths for the sides sheet
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
    await build(studio, sb)
    result = await studio.call("shot.preview", times=[i + 0.5 for i in range(len(azimuths))],
                               width=TILE, height=TILE, out_dir=str(out))
    return [Path(f["path"]) for f in result["frames"]]


def sheet(views: list[Path], out: Path) -> Path:
    """The views side by side, lettered A, B, ... in their top-left corners."""
    tiles = [Image.open(v).convert("RGB") for v in views]
    gap = 8
    board = Image.new("RGB", (len(tiles) * (TILE + gap) - gap, TILE), (255, 255, 255))
    draw = ImageDraw.Draw(board)
    try:
        font = ImageFont.truetype("arialbd.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    for i, tile in enumerate(tiles):
        x = i * (TILE + gap)
        board.paste(tile, (x, 0))
        draw.rectangle((x, 0, x + 48, 52), fill=(0, 0, 0))
        draw.text((x + 10, 4), LETTERS[i], fill=(255, 255, 255), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.save(out)
    return out


async def ups_sheet(studio, source: Path, height: float, folder: Path) -> Path:
    """The model standing each of models.UPS ways up, from the front: A-F."""
    views = []
    for up in models.UPS:
        name = up.replace("+", "pos_").replace("-", "neg_")
        stood = models.normalize(source, folder / f"up_{name}.glb", height, up=up)
        views += await _views(studio, stood, height, (0.0,), folder / f"up_{name}")
    return sheet(views, folder / "ups.png")


async def sides_sheet(studio, source: Path, height: float, up: str, folder: Path) -> Path:
    """The model standing `up`, seen from SIDES (front, its right, back, its left): A-D."""
    stood = models.normalize(source, folder / "stood.glb", height, up=up)
    return sheet(await _views(studio, stood, height, SIDES, folder / "sides"), folder / "sides.png")


# --- Spark's choice ------------------------------------------------------------------------------

class UpChoice(BaseModel):
    reason: str = Field(description="in a sentence: what in the photo and the views decides it (screen, cap, opening, base, text)")
    choice: Literal["A", "B", "C", "D", "E", "F"]


class SideChoice(BaseModel):
    reason: str = Field(description="in a sentence: what in the photo and the views decides it")
    choice: Literal["A", "B", "C", "D"]


SYSTEM = "You are a product photographer staging a 3D model of a product to match its photo exactly."

UP_PROMPT = """The first image is a photo of the product ({category}). The second shows a 3D model of it
standing six different ways (A-F), each on a small grey stand, seen from the front.

Which view stands the model the way the product stands in the photo: upright, not upside down,
not lying on its side or its back? Look at what's at the top and the bottom of the product in the
photo (a cap, a screen's camera notch, cameras, an opening, text reading the right way up) and find
the view with the same thing at its top. Ignore which side faces the camera: that's chosen next."""

SIDE_PROMPT = """The first image is a photo of the product ({category}). The second shows a 3D model of it,
standing upright, from four sides (A-D).

Which view shows the side of the product the photo shows (its front, back or a side: screen or
cameras, label or plain back)? That side will face the camera in the ad."""


def _ask(prompt: str, photo: Path, board: Path, schema: type[BaseModel]) -> BaseModel:
    answer = spark.ask(prompt, images=[photo, board], schema=schema, system=SYSTEM)
    return schema.model_validate(answer.data)


async def stage(studio, run: Run | None, source: Path | str, photo: Path | str, height: float,
                category: str = "product", aspect: float | None = None) -> tuple[str, float]:
    """(up, turn) for models.normalize: the way up and the turn Spark sees
    matching the product in `photo`. If Spark can't answer, the guess from
    the photo's proportions (models.orient, `aspect`), or as the file is."""
    source, photo = Path(source), Path(photo)
    folder = run.folder("stage") if run else Path(source).parent / "stage"
    try:
        ups = await ups_sheet(studio, source, height, folder)
        first = _ask(UP_PROMPT.format(category=category), photo, ups, UpChoice)
        up = models.UPS[LETTERS.index(first.choice)]
        sides = await sides_sheet(studio, source, height, up, folder)
        second = _ask(SIDE_PROMPT.format(category=category), photo, sides, SideChoice)
        turn = -SIDES[LETTERS.index(second.choice)] % 360   # the side seen from azimuth a, turned to face azimuth 0
    except MetaError as e:
        up, turn = models.orient(source, aspect) if aspect else ("+y", 0.0)
        if run:
            run.event("staged", up=up, turn=turn, by="proportions", error=str(e))
        return up, turn
    if run:
        run.event("staged", up=up, turn=turn, by="spark", up_reason=first.reason, side_reason=second.reason,
                  sheets=[p.relative_to(run.root).as_posix() for p in (ups, sides)])
    return up, turn
