"""What the pixels can't say, from Muse Spark vision: the brand's name, each
part's material, the typography, the mood, and what every shot must avoid.

    reading = read(seg, swatches, "perfume bottle")   # a Reading, checked against its schema
    parts = dress(traced.parts, reading)              # the traced parts with their materials

Spark sees the photo and the same photo with the masks drawn on it (so
"body" and "cap" mean the same to it as to us), and the measured palette,
from which it picks each part's colour.
"""

import io

from pydantic import Field

from pipeline.meta import spark
from pipeline.schemas.brand import PartMaterial, Typography
from pipeline.schemas.storyboard import ProfilePart, Strict

from .segment import Segmentation, overlay


class Reading(Strict):
    brand: str = Field(description="the brand name as written on the product; '' if none is legible")
    product_name: str = Field(description="the product's own name if one is written, else ''")
    category: str = Field(description="what it is in a few words: 'eau de parfum', 'olive oil', 'face cream'")
    height: float = Field(gt=0.02, le=0.6, description="its real height in meters, judged from what it is and its proportions")
    materials: list[PartMaterial] = Field(description="one per part named in the request, by that name")
    typography: Typography
    mood: list[str] = Field(min_length=2, max_length=5, description="words for how the brand feels: luxurious, warm, minimal, ...")
    do_not: list[str] = Field(min_length=1, max_length=4, description="what an advert for it must avoid, e.g. "
                                                                         "'bright saturated backgrounds', 'playful motion'")


SYSTEM = ("You are the brand analyst of a studio that makes 3D product adverts. You read product photos for the "
          "renderer and the art director: exactly what is there, judged like a packaging designer. Answer in the schema.")

PROMPT = """The first image is a product photo{hint}. The second is the same photo with its parts marked:
{parts}.

The colours measured from its pixels (hex, role, share of the product):
{palette}

Describe it for a renderer that rebuilds it in 3D:
- materials: one entry for each of these parts, by name: {names}. Its colour comes from the measured palette
  when one fits (shading makes the photo darker or lighter than the material: pick what it is, not its shadows).
- typography: the closest of the renderer's fonts to the label's main lettering: serif (luxury), sans (clean),
  sans_bold (strong), condensed (bold, sporty), script (handwritten); its case and letter spacing.
- mood and do_not: for the art director, grounded in what you see (colours, materials, lettering), not in clichés."""

NAMES = {"body": "body (the product without its cap; the label is printed on it)",
         "cap": "cap (blue)", "label": "label (green, part of the body)"}


def read(seg: Segmentation, swatches, category: str = "", cache_ok: bool = True) -> Reading:
    parts = [p for p in ("body", "cap") if p == "body" or p in seg.parts]
    marked = ["the product outlined in red"] + [NAMES[n] for n in seg.parts if n in NAMES]
    prompt = PROMPT.format(
        hint=f" (it should be a {category})" if category and category != "product" else "",
        parts=", ".join(marked),
        palette="\n".join(f"  {s.hex} {s.role} {s.share:.0%}" for s in swatches),
        names=", ".join(parts))
    result = spark.ask(prompt, images=[seg.photo, _png(overlay(seg))], schema=Reading, system=SYSTEM, cache_ok=cache_ok)
    return result.data


def _png(image) -> bytes:
    out = io.BytesIO()
    image.convert("RGB").save(out, "PNG")
    return out.getvalue()


METAL_PEAK = 0.95     # a light metal's brightest channel, as rendered
DARK_METAL = 0.35     # below this brightest channel a metal is dark (anodised, painted): left as it is


def metal_color(hex_color: str) -> str:
    """A metal's own colour from its photo's: a polished metal mostly
    reflects its surroundings, so its pixels average far darker than the
    metal (#B0B0B1 for aluminium, whose own colour is near #F2F2F3). A light
    metal is brightened until its brightest channel is METAL_PEAK."""
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    peak = max(rgb)
    if peak < DARK_METAL or peak >= METAL_PEAK:
        return hex_color
    r, g, b = (round(min(c * METAL_PEAK / peak, 1) * 255) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def dress(parts: list[ProfilePart], reading: Reading) -> list[ProfilePart]:
    """The parts with the materials Spark read (by name; a part it didn't
    describe keeps what it had); metals in their own colour (metal_color)."""
    by_name = {m.name.lower(): m for m in reading.materials}
    dressed = []
    for part in parts:
        m = by_name.get(part.name)
        if m is None:
            dressed.append(part)
            continue
        color = metal_color(m.color) if m.metallic >= 0.5 else m.color
        dressed.append(part.model_copy(update=dict(color=color, metallic=m.metallic, roughness=m.roughness,
                                                   opacity=m.opacity if m.opacity < 0.98 else None)))
    return dressed
