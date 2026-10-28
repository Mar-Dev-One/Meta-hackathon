"""Muse Spark vision with an answer schema: the product photo read into the
facts the brand analyst needs, as JSON constrained by the schema and
validated with pydantic."""

from pydantic import BaseModel, Field

from _common import product_photo, report

from pipeline.meta import spark


class Part(BaseModel):
    name: str
    color_hex: str = Field(description="#RRGGBB")
    metallic: float = Field(ge=0, le=1)
    roughness: float = Field(ge=0, le=1)
    transparent: bool


class ProductRead(BaseModel):
    category: str
    brand_text: str
    parts: list[Part]
    palette_hex: list[str]
    typography: str
    mood: list[str]


def run() -> dict:
    r = spark.ask("This is a product photo. Describe the product for a 3D artist recreating it.",
                  images=[product_photo()], schema=ProductRead)
    read: ProductRead = r.data
    return {"cached": r.cached, "category": read.category, "brand": read.brand_text,
            "parts": ", ".join(f"{p.name} {p.color_hex} metal {p.metallic} rough {p.roughness}"
                               f"{' clear' if p.transparent else ''}" for p in read.parts),
            "palette": read.palette_hex, "typography": read.typography, "mood": read.mood}


if __name__ == "__main__":
    report(run())
