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
    color: str = Field(pattern=HEX, description="its surface colour; for glass, the glass's own tint (near white "
                                                "for clear glass, green for green glass), not the liquid's")
    metallic: float = Field(ge=0, le=1, description="1 for metal, 0 for everything else")
    roughness: float = Field(ge=0, le=1, description="0.05 polished or glass, 0.3 satin, 0.5 brushed metal, 0.8 matte")
    transmission: float = Field(ge=0, le=1, description="glass and clear plastic you can see into: 1 for clear "
                                                        "glass, 0.9 for tinted glass; 0 for anything opaque (metal, "
                                                        "ceramic, opaque plastic, paper)")
    attenuation_color: str | None = Field(None, pattern=HEX, description="see-through parts: the colour of what "
                                                                         "they hold (amber perfume, green oil), "
                                                                         "seen through them; null for the rest")
    attenuation_distance: float | None = Field(None, gt=0, le=1, description="see-through parts: meters of it after "
                                                                             "which light has fully taken on "
                                                                             "attenuation_color: 0.05 deep, 0.08 rich, "
                                                                             "0.15 pale (a bottle is 5-10 cm across: "
                                                                             "under 0.04 it turns nearly black)")
    clearcoat: float = Field(0, ge=0, le=1, description="a glossy lacquer over it (lacquered caps, coated "
                                                        "packaging): 0..1")

    def surface(self) -> dict:
        """Its finish as Studio part settings (Surface fields)."""
        out = dict(color=self.color, metallic=self.metallic, roughness=self.roughness)
        if self.transmission > 0:
            out.update(transmission=self.transmission)
            if self.attenuation_color and self.attenuation_distance:
                out.update(attenuation_color=self.attenuation_color, attenuation_distance=self.attenuation_distance)
        if self.clearcoat > 0:
            out.update(clearcoat=self.clearcoat, clearcoat_roughness=0.05)
        return out


class Typography(Strict):
    font: Font = Field(description="the closest of the Studio's fonts to the label's lettering")
    case: Literal["upper", "lower", "mixed"]
    tracking: float = Field(ge=-0.2, le=1.5, description="letter spacing in ems, judged from the label")


class BrandProfile(Strict):
    brand: str = Field(description="the brand name as written on the product")
    product_name: str = Field("", description="the product's own name, if any")
    category: str = Field(description="perfume, beverage can, skincare jar, ...")
    template: Literal["perfume", "bottle", "jar", "can", "dropper"] | None = Field(
        None, description="the Studio template closest to its shape; null when the traced profile is used")
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
        looks = {m.name: PartLook(**m.surface()) for m in self.materials}
        return Product(template=self.template, height=self.height, parts=looks, label=self.label)
