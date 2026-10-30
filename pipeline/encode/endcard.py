"""The end card: the ad's last seconds, a still the film dissolves into. The
product as photographed (the brand analyst's packshot), the brand's name
under it in the titles' font, a short line under that, on a calm colour;
the text light or dark, whichever reads on it. Laid out for any frame.

    png = card(sb.end_card, sb.packshot, 1920, 1080, out)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.schemas.storyboard import EndCard

FONTS = Path(__file__).resolve().parents[2] / "Assets" / "fonts"
# The Studio's title fonts (Engine/src/Text), by the storyboard's names.
FONT_FILES = {"serif": "PlayfairDisplay.ttf", "sans": "Montserrat-Regular.ttf", "sans_bold": "Montserrat-SemiBold.ttf",
              "condensed": "Oswald.ttf", "script": "GreatVibes-Regular.ttf"}
TRACKING = {"serif": 0.25, "sans": 0.3, "sans_bold": 0.12, "condensed": 0.06, "script": 0.0}   # in ems
PRODUCT = 0.5     # of the frame's height (at most 1.6 times its width): the packshot's height
NAME = 0.075      # of the shorter side: the name's letter height
LINE = 0.03       # and the tagline's


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    return tuple(int(hex_colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def _ink(background: str) -> tuple[int, int, int]:
    """Text that reads on the background: near-white on dark, near-black on light."""
    r, g, b = (c / 255 for c in _rgb(background))
    return (246, 242, 234) if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5 else (28, 24, 22)


def _spaced(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, tracking: float) -> int:
    """The width of `text` with `tracking` ems between its letters."""
    gap = tracking * font.size
    return round(sum(draw.textlength(ch, font=font) for ch in text) + gap * max(len(text) - 1, 0))


def _write(draw, centre_x: float, top: float, text: str, font, tracking: float, fill) -> None:
    x = centre_x - _spaced(draw, text, font, tracking) / 2
    for ch in text:
        draw.text((x, top), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking * font.size


def card(end: EndCard, packshot: str | None, width: int, height: int, out: Path) -> Path:
    """The end card as a PNG at width x height."""
    image = Image.new("RGB", (width, height), _rgb(end.background))
    draw = ImageDraw.Draw(image)
    short = min(width, height)
    ink = _ink(end.background)
    name_font = ImageFont.truetype(str(FONTS / FONT_FILES[end.font]), round(NAME * short))
    line_font = ImageFont.truetype(str(FONTS / FONT_FILES["sans"]), round(LINE * short))
    name = end.name if end.font == "script" else end.name.upper()

    shot = Image.open(packshot).convert("RGBA") if packshot and Path(packshot).exists() else None
    if shot:   # a tall frame has room for a bigger product than its width alone would give
        scale = PRODUCT * min(height, 1.6 * width) / shot.height
        shot = shot.resize((max(1, round(shot.width * scale)), max(1, round(shot.height * scale))), Image.Resampling.LANCZOS)
    # A column: the product, the name, the line; centred in the frame as a whole.
    gap = 0.05 * short
    heights = ([shot.height, gap] if shot else []) + [name_font.size * 1.3] + ([0.6 * gap, line_font.size * 1.3] if end.tagline else [])
    y = (height - sum(heights)) / 2
    if shot:
        image.paste(shot, (round((width - shot.width) / 2), round(y)), shot)
        y += shot.height + gap
    _write(draw, width / 2, y, name, name_font, TRACKING[end.font], ink)
    y += name_font.size * 1.3 + 0.6 * gap
    if end.tagline:
        _write(draw, width / 2, y, end.tagline, line_font, 0.12, ink)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out
