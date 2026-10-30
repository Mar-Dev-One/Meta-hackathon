"""The storyboard: an ad as data -- its look, its product, its shots, its
titles -- which pipeline.studio.build turns into Studio commands. The
director writes one from a brief; the hand-made ads (pipeline/demos/ads.py)
are written as one.

Field names follow the Studio's command arguments (README.md), so building
is mechanical, and the descriptions are what a model reads when it fills
one in (their JSON Schema is the answer format: pipeline/schemas/export.py).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipeline.catalog.sets import LIGHTS, SURFACES

HEX = r"^#[0-9A-Fa-f]{6}$"
Surface_ = Literal[tuple(SURFACES)]
SURFACE_NOTE = "a real material for it from the set library (its colour comes from the material; `color` is unused): " + \
               "; ".join(f"{name}: {about}" for name, (_, _, _, about) in SURFACES.items())
LIGHT_NOTE = "; ".join(f"{name}: {about}" for name, (_, about) in LIGHTS.items())
HEX_ALPHA = r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"

Ease = Literal["linear", "in", "out", "in_out"]
Font = Literal["serif", "sans", "sans_bold", "condensed", "script"]


class Strict(BaseModel):
    """Unknown fields are an error: a typo shouldn't be silently ignored."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --- The look --------------------------------------------------------------------------------

class Environment(Strict):
    hdri: str = Field("studio", description="the light environment around the product: it lights it, shows in its "
                                            "reflections (glass and metal read by it) and, with show_skybox, is the "
                                            "background. By name: " + LIGHT_NOTE + " (or an HDRI's path under the "
                                            "Studio's assets)")
    use_ibl: bool = Field(True, description="light and reflect with the light environment (keep on for glass and metal)")
    show_skybox: bool = Field(False, description="show the light environment as the background, blurred by sky_blur; "
                                                 "needs look.backdrop null (the backdrop's wall hides it)")
    sky_blur: float = Field(0.35, ge=0, le=1, description="how soft the background environment is: 0.2 recognisable, "
                                                          "0.35 a soft photographic blur, 0.6 only colour and light")
    painted: str | None = Field(None, description="a background painted for this ad by Muse Image, from this "
                                                  "description of a place, its light and colours (e.g. 'a sunlit "
                                                  "limestone bathroom, palm leaf shadows, warm morning light'): shown "
                                                  "behind the product, blurred by sky_blur, and lighting it, in place "
                                                  "of `hdri` (and of the backdrop); for a place the library doesn't have")
    ambient_strength: float = Field(0.06, ge=0, le=4, description="0.05 dark and moody, 0.6 bright and airy")
    exposure: float = Field(1.0, gt=0, le=16)
    bloom: float = Field(0.08, ge=0, le=1, description="glow around bright highlights; 0.03 clean, 0.14 dreamy or neon")
    tonemap: Literal["agx", "aces", "neutral"] = Field("agx", description="agx: soft filmic; aces: contrasty; neutral: colours as authored (bright, clean looks)")
    ssao: bool = True


class Backdrop(Strict):
    color: str = Field("#0A0A0C", pattern=HEX, description="the cyclorama's colour (sRGB)")
    roughness: float = Field(0.6, ge=0, le=1)
    surface: Surface_ | None = Field(None, description="null: plain `color`. Or " + SURFACE_NOTE)
    texture: str | None = Field(None, description="an image to cover it with (a path), e.g. from Muse Image")


class Pedestal(Strict):
    width: float = Field(0.32, gt=0.02, le=3, description="diameter, meters; a little wider than the product")
    height: float = Field(0.2, gt=0.01, le=2, description="meters; the product stands on it")
    color: str = Field("#0E0E10", pattern=HEX)
    roughness: float = Field(0.85, ge=0, le=1, description="keep high (0.8+) under rim lights, or its top glares")
    surface: Surface_ | None = Field(None, description="null: plain `color`. Or a material (see look.backdrop.surface); "
                                                       "a low wide pedestal of one is a slab to stand the product on")


class Lighting(Strict):
    preset: Literal["three_point", "rim_dark", "high_key", "top_soft", "split", "neon_dual"] = Field(
        description="rim_dark: luxury, moody; high_key: clean, bright (light backdrop); top_soft: natural, skylight; "
                    "split: dramatic; neon_dual: bold, energetic; three_point: neutral")
    intensity: float = Field(1.0, ge=0, le=20, description="times the preset's brightness")
    turn: float = Field(0.0, ge=-360, le=360, description="degrees to turn the whole setup around the product")
    warmth: float = Field(0.0, ge=-1, le=1, description="-1 cooler .. 1 warmer")
    fade_in: float | None = Field(None, gt=0, le=10, description="seconds over which every light rises from dark at the start (a reveal)")
    glow: float | None = Field(None, ge=0, le=20, description="a soft pool of light on the wall behind the product: "
                                                              "glass lights up in it in the colour of what it holds "
                                                              "(a backlit bottle); 1 subtle, 2-3 strong; for glass "
                                                              "on a dark set")
    glow_color: str | None = Field(None, pattern=HEX, description="the glow's colour (default warm)")


class Look(Strict):
    environment: Environment = Field(default_factory=Environment)
    background: list[float] = Field(default=[0.004, 0.004, 0.006], min_length=3, max_length=3,
                                    description="linear RGB where nothing is drawn (behind the backdrop's edges)")
    backdrop: Backdrop | None = Field(default_factory=Backdrop, description="the floor curving up into a wall behind; "
                                      "null: none, the light environment is the background (set environment.show_skybox, "
                                      "which removes the backdrop by itself)")
    pedestal: Pedestal | None = Field(default_factory=Pedestal, description="null: the product stands on the floor")
    lighting: Lighting

    @model_validator(mode="after")
    def _background_or_wall(self):
        """The light environment as the background needs no wall in front of
        it: an omitted backdrop (the default) would hide it. A painted
        background is always the background."""
        if self.environment.painted:
            self.environment.show_skybox = True
        if self.environment.show_skybox:
            self.backdrop = None
        return self


# --- The product -------------------------------------------------------------------------------

class Surface(Strict):
    """A part's finish: what product.create takes for each part. Unset = the
    template's (or, for glass, clear coat and specular, not used)."""
    color: str | None = Field(None, pattern=HEX, description="sRGB")
    opacity: float | None = Field(None, ge=0.02, le=1, description="below 1: see-through by fading out (a ghost, not "
                                                                   "glass; for glass use transmission)")
    metallic: float | None = Field(None, ge=0, le=1)
    roughness: float | None = Field(None, ge=0, le=1, description="0 mirror .. 1 matte; glass ~0.05, gold ~0.2")
    transmission: float | None = Field(None, ge=0, le=1, description="glass and clear liquids: 0.9-1 shows the set "
                                                                     "through it, bent and tinted (then keep opacity unset)")
    ior: float | None = Field(None, ge=1, le=3, description="glass: index of refraction, 1.5 glass, 1.33 water")
    thickness: float | None = Field(None, ge=0, le=5, description="glass: meters light travels through it (default "
                                                                  "the part's width: a solid bottle of liquid)")
    attenuation_color: str | None = Field(None, pattern=HEX, description="glass: the colour light takes on through "
                                                                         "it, i.e. the liquid's (amber perfume, green oil)")
    attenuation_distance: float | None = Field(None, gt=0, le=100, description="glass: meters of it after which light "
                                                                               "has fully taken on attenuation_color: "
                                                                               "0.05 deep, 0.08 rich, 0.15 pale (under "
                                                                               "0.04 a bottle turns nearly black); "
                                                                               "needed with it")
    clearcoat: float | None = Field(None, ge=0, le=1, description="a glossy lacquer over it (lacquered caps, coated "
                                                                  "labels), 0..1")
    clearcoat_roughness: float | None = Field(None, ge=0, le=1)
    specular: float | None = Field(None, ge=0, le=1, description="strength of a non-metal's reflections (default 1)")
    specular_color: str | None = Field(None, pattern=HEX, description="tint of a non-metal's reflections")


class PartLook(Surface):
    pass


class Label(Strict):
    image: str = Field(description="path to the label artwork (PNG with transparent corners, or JPG)")
    part: str = Field("body", description="the part it wraps")
    from_: float | None = Field(None, alias="from", description="meters up the product where it starts (default: the template's)")
    to: float | None = Field(None, description="meters up where it ends")
    arc: float = Field(110, ge=5, le=360, description="degrees it wraps around the front; 360 all the way round")


class ProfilePart(Surface):
    name: str
    profile: list[list[float]] = Field(min_length=2, description="[radius, height] in meters, bottom to top")


class Product(Strict):
    template: Literal["perfume", "bottle", "jar", "can", "dropper"] | None = Field(
        None, description="the shape; null with `profile_parts` for a shape traced from a photo")
    height: float | None = Field(None, gt=0.005, le=5, description="meters (templates have a typical size)")
    width: float | None = Field(None, gt=0.005, le=5, description="meters across at the widest")
    parts: dict[str, PartLook] = Field(default_factory=dict, description="template parts' looks by name: body, cap, lid, collar, bulb")
    profile_parts: list[ProfilePart] | None = Field(None, description="the shape as profiles (from the brand analyst), instead of a template")
    model: str | None = Field(None, description="the product as a 3D model file (.glb: meters, Y up, base at the "
                                                "origin), for shapes that aren't round; instead of a template "
                                                "or profiles (pipeline.studio.models)")
    finish: Surface | None = Field(None, description="a model's finish over its own texture: metallic, roughness, "
                                                     "clear coat, glass")
    label: Label | None = None

    @model_validator(mode="after")
    def _shape(self):
        if sum(x is not None for x in (self.template, self.profile_parts, self.model)) != 1:
            raise ValueError("give exactly one of `template`, `profile_parts` and `model`")
        return self


# --- Shots, titles, tracks ----------------------------------------------------------------------

class CameraMove(Strict):
    move: Literal["static", "orbit", "dolly", "crane", "truck", "reveal", "zoom"] = Field(
        description="static: holds; orbit: circles it; dolly: pushes in/out; crane: rises or drops; "
                    "truck: slides past; reveal: aim pans onto it; zoom: lens only")
    ease: Ease = "in_out"
    fill: float = Field(0.6, ge=0.05, le=5, description="share of the frame's height the product fills; 0.45 wide, 0.6 medium, 0.9 close, over 0.97 crops it (a close-up)")
    azimuth: float = Field(0, ge=-360, le=360, description="degrees around: 0 front, 90 its right, -90 its left")
    elevation: float = Field(8, ge=-85, le=85, description="degrees above; low angles (2-8) feel heroic")
    fov_degrees: float = Field(30, ge=1, le=179, description="vertical lens angle; 30 is a product lens")
    to_azimuth: float | None = Field(None, description="orbit: where it ends")
    from_fill: float | None = Field(None, ge=0.05, le=5, description="dolly: framing at the start")
    to_fill: float | None = Field(None, ge=0.05, le=5, description="dolly: framing at the end")
    from_elevation: float | None = Field(None, ge=-85, le=85, description="crane: start")
    to_elevation: float | None = Field(None, ge=-85, le=85, description="crane: end")
    travel: float | None = Field(None, description="truck: meters moved right (negative left)")
    from_: Literal["above", "below", "left", "right"] | None = Field(None, alias="from", description="reveal: where the aim starts")
    from_fov: float | None = Field(None, ge=1, le=179, description="zoom: start lens")
    to_fov: float | None = Field(None, ge=1, le=179, description="zoom: end lens")
    aperture: float | None = Field(None, ge=0, le=64, description="depth of field, the f-number: the product's front "
                                                                  "stays sharp and what's behind softens; unset or 0 "
                                                                  "= all sharp, 2-2.8 a very soft background "
                                                                  "(close-ups, heroes), 4-5.6 a softened set")

    def max_fill(self) -> float:
        """The most of the frame's height the product fills during the move
        (a dolly's defaults as camera.move applies them)."""
        if self.move == "dolly":
            return max(self.from_fill if self.from_fill is not None else 0.6 * self.fill,
                       self.to_fill if self.to_fill is not None else self.fill)
        return self.fill


class ProductMotion(Strict):
    """The product moving during a shot (it's back at rest at the next cut)."""
    move: Literal["turn", "float", "drop", "tilt"] = Field(
        description="turn: turns on its own axis and settles facing front by the end (shows the label coming "
                    "round); float: rises gently, weightless, through the shot; drop: falls onto its stand in "
                    "the shot's first 40%, then holds still; tilt: leans gently towards the camera and back")
    amount: float | None = Field(None, ge=-720, le=720,
                                 description="turn: degrees it turns (default 45; 360 a full spin; negative the other "
                                             "way); tilt: degrees it leans (default 8); float: how far it rises and "
                                             "drop: how far above it starts, as a share of its height (defaults "
                                             "0.08 and 0.35)")


class Shot(Strict):
    id: str = Field(description="s1, s2, ...")
    intent: str = Field(description="what the shot is for, in a sentence: the critic judges it against this")
    duration: float = Field(gt=0.2, le=30, description="seconds; shots run back to back from 0")
    camera: CameraMove
    motion: ProductMotion | None = Field(None, description="the product moving in this shot; null: it stands still")


class Title(Strict):
    text: str = Field(min_length=1, max_length=255)
    font: Font = Field(description="serif: luxury; sans: clean; sans_bold: strong; condensed: bold, sporty; script: elegant, handwritten")
    size: float = Field(ge=0.01, le=0.3, description="letter height as a share of the frame's height: 0.07 a name, 0.03 a tagline")
    y: float = Field(ge=0.05, le=0.95, description="vertical centre as a share of the frame's height (0 top); keep clear of the product")
    color: str = Field(pattern=HEX_ALPHA)
    tracking: float = Field(0.0, ge=-0.2, le=1.5, description="extra letter spacing in ems; 0.2-0.3 for wide luxury capitals")
    start: float = Field(ge=0, description="seconds: when it starts fading in")
    fade: float = Field(0.7, gt=0, le=5, description="seconds to fade in")


class Key(Strict):
    t: float = Field(ge=0)
    value: float | list[float]
    ease: Literal["linear", "in", "out", "in_out", "step"] = "linear"


class Track(Strict):
    """Anything else animated: e.g. a light rising at a cut (the product's own moves are Shot.motion)."""
    entity: str
    component: str
    field: str
    keys: list[Key] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_key_per_time(self):
        times = [k.t for k in self.keys]
        if len(set(times)) != len(times):
            raise ValueError(f"two keys of {self.entity}.{self.field} are at the same time ({times}): one key per "
                             f"time; to hold a value from the start, give one key")
        return self


# --- The storyboard -------------------------------------------------------------------------------

class Storyboard(Strict):
    title: str = Field(description="a working name for the ad")
    brief: str = Field(description="the brief it answers")
    style: str = Field(description="the look in a few words: 'dark and moody luxury'")
    fps: int = Field(30, ge=12, le=60)
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"
    look: Look
    product: Product
    shots: list[Shot] = Field(min_length=1, max_length=12)
    titles: list[Title] = Field(default_factory=list, max_length=6)
    tracks: list[Track] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return round(sum(s.duration for s in self.shots), 3)

    def shot_starts(self) -> list[float]:
        starts, t = [], 0.0
        for s in self.shots:
            starts.append(round(t, 3))
            t += s.duration
        return starts

    @model_validator(mode="after")
    def _consistent(self):
        ids = [s.id for s in self.shots]
        if len(set(ids)) != len(ids):
            raise ValueError(f"shot ids must be unique: {ids}")
        for t in self.titles:
            if t.start >= self.duration:
                raise ValueError(f"title {t.text!r} starts at {t.start} s, after the ad ends ({self.duration} s)")
        return self
