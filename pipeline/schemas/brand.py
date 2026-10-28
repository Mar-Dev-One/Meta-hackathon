"""The brand profile: what the brand analyst reads from product photos, and
what every shot must follow. It fills a storyboard's `product` (shape,
materials, label) and guides its look (palette, typography, mood)."""

from typing import Literal

from pydantic import Field

from .storyboard import HEX, Font, Label, PartLook, Product, ProfilePart, Strict


class Swatch(Strict):
    hex: str = Field(pattern=HEX)
    role: Literal["product", "accent", "label", "text", "background"] = Field(
        description="where the colour belongs: the product's main colour, a highlight, the label, its text, or the setting")
    share: float = Field(ge=0, le=1, description="share of the product's pixels with this colour")


class PartMaterial(Strict):
    name: str = Field(description="body, cap, lid, ...")
    looks_like: str = Field(description="the material in a few words: 'clear glass holding amber liquid', 'brushed aluminium'")
    color: str = Field(pattern=HEX, description="the colour to render it: for clear glass holding a liquid, the liquid's")
    metallic: float = Field(ge=0, le=1, description="1 for metal, 0 for everything else")
    roughness: float = Field(ge=0, le=1, description="0.05 polished or glass, 0.3 satin, 0.5 brushed metal, 0.8 matte")
    opacity: float = Field(ge=0.02, le=1, description="1 for anything you can't see through, dark glass and dark "
                                                      "liquids included; clear glass holding a light liquid 0.75-0.9; "
                                                      "empty clear glass 0.2-0.4")


class Typography(Strict):
    font: Font = Field(description="the closest of the Studio's fonts to the label's lettering")
    case: Literal["upper", "lower", "mixed"]
    tracking: float = Field(ge=-0.2, le=1.5, description="letter spacing in ems, judged from the label")


class BrandProfile(Strict):
    brand: str = Field(description="the brand name as written on the product")
    product_name: str = Field("", description="the product's own name, if any")
    category: str = Field(description="perfume, beverage can, skincare jar, ...")
    template: Literal["perfume", "bottle", "jar", "can", "dropper"] | None = Field(
        description="the Studio template closest to its shape; null when the traced profile is used")
    height: float = Field(gt=0.005, le=5, description="real height in meters (estimated from the category)")
    profile_parts: list[ProfilePart] | None = Field(None, description="the shape traced from the photo's silhouette")
    materials: list[PartMaterial]
    palette: list[Swatch] = Field(min_length=1, max_length=8)
    typography: Typography
    mood: list[str] = Field(min_length=1, max_length=6, description="a few words: luxurious, warm, minimal, ...")
    do_not: list[str] = Field(default_factory=list, description="things every shot must avoid, e.g. 'bright saturated colours'")
    label: Label | None = Field(None, description="the label cut from the photo and unrolled, and where it wraps")
    logo_image: str | None = Field(None, description="path to the logo cut from the photo")
    photos: list[str] = Field(default_factory=list, description="the photos it was read from")

    def product(self) -> Product:
        """The storyboard's product: the traced shape (or the template, its
        parts dressed in the materials), with the label."""
        if self.profile_parts:
            return Product(template=None, profile_parts=self.profile_parts, label=self.label)
        looks = {m.name: PartLook(color=m.color, metallic=m.metallic, roughness=m.roughness,
                                  opacity=m.opacity if m.opacity < 0.98 else None) for m in self.materials}
        return Product(template=self.template, height=self.height, parts=looks, label=self.label)
