"""Brief → storyboard: Muse Spark plans the ad from the brief, the brand
profile, the shot grammar and the style library; code checks it.

    sb = await write("luxury perfume ad, dark and moody, 15 seconds", profile, studio=studio, run=run)

Spark writes a Plan (a Storyboard without the product, which is the brand
profile's). It's validated by the schema and then checked in code against
the craft rules a schema can't hold (lengths add up, the ending is the hero
with the brand's name, titles fit the frame as the Studio measures them).
Whatever is wrong goes back to Spark with its answer, up to `tries` times.
"""

import json
import re
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import Field, ValidationError

from pipeline.catalog.sets import surface_colour
from pipeline.encode.music import cut_to_beat
from pipeline.meta import spark
from pipeline.schemas import BrandProfile, Storyboard
from pipeline.schemas.storyboard import EndCard, Look, Shot, Strict, Title, Track
from pipeline.studio import models
from pipeline.studio.build import ASPECTS, build, motion_keys, product_size

from . import grammar
from .styles import STYLES

FRAMES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
DEFAULT_SECONDS = 15.0

SHOT_MIN, SHOT_MAX = 1.2, 5.0
HERO_MIN = 2.5            # the last shot, seconds
HERO_AZIMUTH = 25         # degrees from the front
FLAT, FLAT_ELEVATION = 0.75, 30   # a model lower than this share of its narrower width (from above) lies flat:
                                  # look down on it from at least this high
THIN, THIN_AZIMUTH = 0.45, 30   # a model thinner than this share of its length (from above): keep cameras this
                                # many degrees from looking along its length, or it's seen edge-on
TITLE_DELAY = 0.4         # the name appears at least this long after the hero starts
TITLE_SEEN = 0.8          # ... and at least this long before the end
MAX_TITLES = 2            # titles stay on once in, so this many are on screen together
SEE_THROUGH = 0.5         # a material this transmissive is glass; this metallic, metal
SEPARATION = 15           # the product's and the backdrop's lightness (L*, 0-100) at least this far apart
DARK_SET = 25             # a backdrop darker than this (L*) is a dark set
GLASS_LIGHT = 1.5         # glass on a dark set needs the lights at least this strong (and a glow)
DARK_PRODUCT = 35         # a product darker than this (L*) in front of an environment background ...
DARK_LIGHT, DARK_EXPOSURE = 1.8, 0.8   # ... needs lights this strong and the environment this dim
TITLE_CONTRAST = 3.0      # a title against what's behind it, as a contrast ratio
CHECKS = Path("cache/title_check")   # where the frames behind the titles are rendered to be measured
TITLE_BANDS = ((0.0, 0.27), (0.72, 1.0))  # where a title's centre may be (above or below the product)
TITLE_CLEAR = 0.02        # of the frame's height between a title's box and the product (centred, `fill` tall)
PEDESTAL_WIDTH = (1.2, 7.0)   # a pedestal's width, in product widths: wider than it, not a dance floor
PEDESTAL_HEIGHT = 1.5         # at most this many product heights tall, or it upstages the product


class DirectorError(Exception):
    """No valid storyboard after every try; the last problems are in the message."""


class Plan(Strict):
    title: str = Field(description="a working name for the ad")
    style: Literal[tuple(STYLES)] = Field(description="the style from the library it starts from")
    look: Look
    shots: list[Shot] = Field(min_length=2, max_length=12)
    titles: list[Title] = Field(max_length=MAX_TITLES)
    tracks: list[Track] = Field(default_factory=list, description="other animation, e.g. a light rising at a cut")
    end_card: EndCard | None = Field(None, description="the still the ad ends on, after the last shot; null: none")


SYSTEM = ("You are the director of a studio that makes short 3D product adverts. You plan an ad as shots for a "
          "renderer whose every option is in the shot grammar, and you only use what it offers. The brief comes "
          "first, then the brand profile and the ad-craft rules. Answer in the schema.")

PROMPT = """# The brief

{brief}

Length: {seconds:g} seconds. Frame: {aspect}.

# The brand profile (from its product photo)

{profile}

The product (its 3D shape, materials and label) is built from this profile; you plan everything around it,
sized for it (a pedestal a little wider than it and not much taller).

Its do_not list is the brand's usual taste: follow it, unless the brief asks for something it rules out (say,
a bright summer campaign for a brand that's usually muted). Then the brief wins, and the brand stays
recognisable through its name, its type and its palette's accents.

# The style library (whole looks; start from one, adapt its colours to the palette)

{styles}

{grammar}
# Your answer

A Plan: a working title, the style you start from, the look (set, light, environment), the shots in
order (their durations adding up to {seconds:g} s), the titles and any extra animation."""


def seconds_in(brief: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:s\b|sec\b|secs\b|seconds?\b)", brief, re.IGNORECASE)
    return float(m.group(1)) if m else None


def aspect_in(brief: str) -> str:
    text = brief.lower()
    if any(w in text for w in ("vertical", "9:16", "portrait", "reel", "story", "stories", "tiktok", "shorts")):
        return "9:16"
    if any(w in text for w in ("square", "1:1")):
        return "1:1"
    return "16:9"


def _profile_text(p: BrandProfile | None) -> str:
    if p is None:
        return "(none: the storyboard's product, colours and style stand for the brand)"
    height, width = product_size(p.product())
    edges = edge_on(p.product())
    facts = {"brand": p.brand, "product_name": p.product_name, "category": p.category,
             "size": f"{height * 100:.1f} cm tall, {width * 100:.1f} cm wide",
             **({"flat": f"it lies low and flat: seen from near level it's only its edge, so look down on it, every "
                         f"camera at least {FLAT_ELEVATION:g} degrees above it"} if lies_flat(p.product()) else {}),
             **({"thin": f"seen from above it's much thinner one way than the other: from azimuth "
                         f"{edges[0] % 360:.0f} or {edges[1] % 360:.0f} it's seen edge-on, so keep every camera at "
                         f"least {THIN_AZIMUTH:g} degrees from those (azimuth, and an orbit's to_azimuth)"}
                if edges else {}),
             "materials": [f"{m.name}: {m.looks_like} ({m.color})" for m in p.materials],
             "palette": [f"{s.hex} {s.role} {s.share:.0%}" for s in p.palette],
             "typography": p.typography.model_dump(), "mood": p.mood, "do_not": p.do_not,
             "label": f"wraps {p.label.arc:g} degrees round the body" if p.label else "none"}
    return json.dumps(facts, indent=1)


def _styles_text() -> str:
    return "\n".join(json.dumps({"name": s.name, "use_for": s.use_for, "look": s.look.model_dump(exclude_none=True),
                                 "title": s.title.model_dump(), "shot_seconds": s.shot_seconds, "moves": s.moves,
                                 "ease": s.ease, "aperture": s.aperture}, separators=(",", ":")) for s in STYLES.values())


def on_beat(sb: Storyboard) -> Storyboard:
    """The storyboard cut on the music's beats (pipeline.encode.music),
    within the craft rules' shot lengths."""
    return cut_to_beat(sb, SHOT_MIN, SHOT_MAX, HERO_MIN)


def assemble(plan: Plan, profile: BrandProfile, brief: str, aspect: str) -> Storyboard:
    data = plan.model_dump(by_alias=True, exclude_none=True)
    data.update(brief=brief, aspect=aspect, product=profile.product().model_dump(by_alias=True),
                packshot=profile.packshot)
    return Storyboard.model_validate(data)


def lies_flat(product) -> bool:
    """Whether the product (a 3D model) lies low and flat (a controller on
    its back, a watch laid down, a tablet): seen from near level it's only
    its edge."""
    if not product.model:
        return False
    across = models.footprint(product.model)[1]   # its narrower way from above: low against both ways is flat
    return product_size(product)[0] < FLAT * across


def _elevations(camera) -> list[float]:
    """The heights a shot's camera passes through: its own, and a crane's start and end."""
    if camera.move == "crane":
        return [camera.from_elevation if camera.from_elevation is not None else camera.elevation - 15,
                camera.to_elevation if camera.to_elevation is not None else camera.elevation + 25]
    return [camera.elevation]


def edge_on(product) -> list[float] | None:
    """For a thin product (a 3D model much thinner one way than the other
    seen from above: a watch, a phone, a controller, a shoe), the two
    azimuths a camera sees it edge-on from (looking along its length); None
    for one that reads from any side."""
    if not product.model:
        return None
    length, thickness, azimuth = models.footprint(product.model)
    return [azimuth, azimuth + 180] if thickness < THIN * length else None


def _from_edge(azimuth: float, edges: list[float]) -> float:
    """Degrees between a camera's azimuth and the nearest edge-on one."""
    return min(abs((azimuth - e + 180) % 360 - 180) for e in edges)


def _azimuths(camera) -> list[float]:
    """The azimuths a shot's camera passes through: its own, and where an orbit ends."""
    if camera.move == "orbit":
        return [camera.azimuth, camera.to_azimuth if camera.to_azimuth is not None else camera.azimuth + 60]
    return [camera.azimuth]


def problems(sb: Storyboard, profile: BrandProfile | None, seconds: float) -> list[str]:
    """The craft rules in code: what's wrong with the storyboard, each said
    so it can be fixed."""
    out = []
    if abs(sb.length - seconds) > 0.5:
        card = f" and the end card's {sb.end_card.seconds:g} s" if sb.end_card else ""
        out.append(f"the shots ({sb.duration:g} s){card} add up to {sb.length:g} s, but the ad is {seconds:g} s: "
                   f"change their durations")
    for shot in sb.shots:
        if not SHOT_MIN <= shot.duration <= SHOT_MAX:
            out.append(f"shot {shot.id} lasts {shot.duration:g} s: keep shots between {SHOT_MIN:g} and {SHOT_MAX:g} s")
    for a, b in zip(sb.shots, sb.shots[1:]):
        if a.camera.move == b.camera.move:
            out.append(f"shots {a.id} and {b.id} are both {a.camera.move}: consecutive shots move differently")

    for shot in sb.shots if lies_flat(sb.product) else ():
        low = [e for e in _elevations(shot.camera) if e < FLAT_ELEVATION]
        if low:
            out.append(f"shot {shot.id} puts the camera {low[0]:g} degrees above the product, which lies flat: from "
                       f"that low it's seen edge-on. Keep every elevation (and a crane's from_ and to_elevation, which "
                       f"are elevation - 15 and + 25 unless given) at least {FLAT_ELEVATION:g}, looking down on it")
    edges = edge_on(sb.product)
    for shot in sb.shots if edges else ():
        near = [a for a in _azimuths(shot.camera) if _from_edge(a, edges) < THIN_AZIMUTH]
        if near:
            out.append(f"shot {shot.id} puts the camera at azimuth {near[0]:g}, which sees the thin product nearly "
                       f"edge-on (it's edge-on from {edges[0] % 360:.0f} and {edges[1] % 360:.0f}): keep every azimuth, "
                       f"and an orbit's to_azimuth (azimuth + 60 unless given), at least {THIN_AZIMUTH:g} degrees from "
                       f"those")

    hero, hero_start = sb.shots[-1], sb.shot_starts()[-1]
    if hero.camera.move != "static" or abs(hero.camera.azimuth) > HERO_AZIMUTH or hero.duration < HERO_MIN:
        out.append(f"the last shot ({hero.id}) must be the hero: a static move from the front (azimuth within "
                   f"{HERO_AZIMUTH} degrees of 0), at least {HERO_MIN:g} s long")

    if profile and profile.brand:
        brand = profile.brand.casefold().replace(" ", "")
        named = [t for t in sb.titles if brand in t.text.casefold().replace(" ", "")]
        if not named:
            out.append(f"no title shows the brand name {profile.brand!r}")
        elif not any(hero_start + TITLE_DELAY <= t.start <= sb.duration - TITLE_SEEN for t in named):
            out.append(f"the brand name's title must start in the hero shot, between {hero_start + TITLE_DELAY:g} s "
                       f"and {sb.duration - TITLE_SEEN:g} s")
    for t in sb.titles:
        if t.font == "script" and t.text.isupper():
            out.append(f"title {t.text!r} is script in capitals: write it in mixed case, or use another font")
        if not any(lo <= t.y <= hi for lo, hi in TITLE_BANDS):
            (above_lo, above_hi), (below_lo, below_hi) = TITLE_BANDS
            out.append(f"title {t.text!r} is centred at y {t.y:g}, over the product: put it at y "
                       f"{max(above_lo, 0.05):g}-{above_hi:g} (above) or {below_lo:g}-{min(below_hi, 0.95):g} (below)")
    if sb.look.pedestal:
        height, width = product_size(sb.product)
        ped = sb.look.pedestal
        lo, hi = PEDESTAL_WIDTH
        if not lo * width <= ped.width <= hi * width or ped.height > PEDESTAL_HEIGHT * height:
            out.append(f"the pedestal ({ped.width * 100:.0f} cm wide, {ped.height * 100:.0f} cm tall) is out of "
                       f"proportion with the product ({width * 100:.1f} cm wide, {height * 100:.1f} cm tall): make it "
                       f"{lo * width * 100:.0f}-{hi * width * 100:.0f} cm wide and at most "
                       f"{PEDESTAL_HEIGHT * height * 100:.0f} cm tall (about {2.5 * width * 100:.0f} x "
                       f"{0.6 * height * 100:.0f} cm suits most), or set it to null")
    moved = set(motion_keys(sb))
    for track in sb.tracks:
        if track.entity != "product" and not track.entity.startswith("light_"):
            out.append(f"a track animates {track.entity!r}: tracks may only animate the product or the lights")
        if track.entity == "product" and track.component == "Transform" and track.field in moved:
            out.append(f"a track and the shots' motion both move the product's {track.field}: use the shots' "
                       f"motion and remove the track")
        if any(k.t > sb.duration for k in track.keys):
            out.append(f"a track on {track.entity} has keys after the end ({sb.duration:g} s)")
    return out


def _luminance(hex_colour: str) -> float:
    """Relative luminance (0 black .. 1 white) of an sRGB "#RRGGBB"."""
    channels = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lightness(hex_colour: str) -> float:
    """Perceived lightness, L* (0 black .. 100 white)."""
    y = _luminance(hex_colour)
    return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y


def _contrast(a: str, b: str) -> float:
    """The contrast ratio of two colours (1 .. 21; text reads from about 3)."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _set_colour(part) -> str:
    """A backdrop's or pedestal's colour as seen: its surface's, or its own."""
    return surface_colour(part.surface) if part.surface else part.color


def light_problems(sb: Storyboard, profile: BrandProfile | None) -> list[str]:
    """Light that sells the material, as rules: what glass, metal and the
    product's tone need from the set to read, and titles that can be read.
    Rules of taste, unlike problems(): told to Spark every time, but a last
    attempt with only these left is kept (with them as warnings), not failed."""
    out = []
    if profile is None:
        return out
    glass = any(m.transmission >= SEE_THROUGH for m in profile.materials)
    metal = any(m.metallic >= SEE_THROUGH for m in profile.materials)
    env, lighting = sb.look.environment, sb.look.lighting
    # What the set reads as: a surface's own colour, the plain colour, or (no backdrop, the light
    # environment behind) nothing these rules can judge. Titles against the set: title_contrast_problems.
    backdrop = _set_colour(sb.look.backdrop) if sb.look.backdrop else None
    if (glass or metal) and not env.use_ibl:
        out.append(f"the product is {'glass' if glass else 'metal'}, which shows what's around it: keep "
                   f"look.environment.use_ibl on, or it renders black")
    tone = next((s.hex for s in profile.palette if s.role == "product"), None)
    if tone and backdrop and abs(_lightness(tone) - _lightness(backdrop)) < SEPARATION:
        out.append(f"the product ({tone}, lightness {_lightness(tone):.0f}) and the backdrop ({backdrop}, "
                   f"{_lightness(backdrop):.0f}) are too close in tone: it melts into the set. Make the backdrop "
                   f"clearly darker or lighter (at least {SEPARATION} apart, out of 100), or another surface")
    if tone and env.show_skybox and _lightness(tone) < DARK_PRODUCT and \
            (lighting.intensity < DARK_LIGHT or env.exposure > DARK_EXPOSURE):
        out.append(f"the product is dark ({tone}, lightness {_lightness(tone):.0f}) and stands in front of a light "
                   f"environment: backlit like that it reads as a silhouette. Light it strongly (look.lighting.intensity "
                   f"at least {DARK_LIGHT:g}) and dim the background (environment.exposure at most {DARK_EXPOSURE:g})")
    if glass and backdrop and _lightness(backdrop) < DARK_SET and (lighting.intensity < GLASS_LIGHT or not lighting.glow):
        out.append(f"glass on a dark set reads black unless it's lit: set look.lighting.intensity to at least "
                   f"{GLASS_LIGHT:g} and give it a glow (2-3), or put a bright light environment behind it (backdrop "
                   f"null, show_skybox); a lighter backdrop doesn't help, the glass blends into it")
    for t in sb.titles:
        on_pedestal = next((shot for shot in shots_from(sb, t.start) if _over_pedestal(sb, shot, t)), None)
        if on_pedestal:
            top, bottom = _pedestal_rows(sb, on_pedestal)
            room = f"; or below it (y {bottom + 0.04:.2f} or lower)" if bottom < 0.9 else ""
            out.append(f"title {t.text!r} sits on the pedestal's face in {on_pedestal.id}: there the pedestal covers "
                       f"y {top:.2f}-{min(bottom, 1):.2f} of the frame. Put the title above the product (y "
                       f"{max(TITLE_BANDS[0][0], 0.05):g}-{TITLE_BANDS[0][1]:g}){room}; or frame that shot wider "
                       f"(lower fill) with a low slab so there's set below it")
    return out


HERO_FIXES = {   # what to change when the critic's measurements of the hero find a problem, by its category
    "brand": "the light around the product tints it: choose a light environment nearer its colours (a neutral "
             "studio for a cool or dark product), light it more strongly with the lights (look.lighting.intensity), "
             "or dim the environment (environment.exposure)",
    "lighting": "light it so it reads: more light on it (look.lighting.intensity, or a preset that lights its front), "
                "less when it's blown out, or a background that separates from it",
    "product_visibility": "frame the hero so the product is whole and clearly seen",
}


async def hero_problems(studio, sb: Storyboard) -> list[str]:
    """The hero shot measured as the critic measures every shot (pipeline.
    agents.critic.measure), at planning time: the product's exact pixels
    (rendered with it, alone and without it), then whether its colours are
    the brand's, its outline separates from the background, its pixels
    aren't crushed or blown. With the critic loop off, the critic's eye on
    every ad still. Rules of taste."""
    from pipeline.agents.critic.measure import Frame, _passes, flags_for, measure_frame, product_mask, \
        storyboard_colours   # here: the critic's module imports this one's neighbours

    width, height = 640, round(640 / ASPECTS[sb.aspect])
    t = sb.shot_starts()[-1] + 0.5 * sb.shots[-1].duration
    await build(studio, sb)
    shown, paths, alone, empty = await _passes(studio, [t], width, height, CHECKS.resolve() / "hero", 16)
    bounds = await studio.call("shot.bounds", entity="product", t=t, width=width, height=height)
    frame = Frame(time=t, path=paths[0], bounds=bounds)
    measure_frame(frame, shown[0], product_mask(alone[0], empty[0], bounds.get("box")), storyboard_colours(sb), {})
    flags = flags_for(frame, is_last=True, fade_in=sb.look.lighting.fade_in or 0.0)
    return [f"in the hero ({sb.shots[-1].id}), as rendered: {f.problem}. {HERO_FIXES.get(f.category, '')}".rstrip()
            for f in flags if f.category in HERO_FIXES]


async def title_contrast_problems(studio, sb: Storyboard) -> list[str]:
    """Titles hard to read against what's really behind them: the scene
    built and rendered at each title's start (it's still invisible then),
    and the picture under its box averaged, whatever the set is (a colour,
    a surface, a light environment, a painting). Rules of taste."""
    width, height = 640, round(640 / ASPECTS[sb.aspect])
    await build(studio, sb)
    frames = (await studio.call("shot.preview", times=[t.start for t in sb.titles], width=width, height=height,
                                out_dir=str(CHECKS.resolve())))["frames"]
    out = []
    for t, frame in zip(sb.titles, frames):
        box = (await studio.call("text.measure", text=t.text, font=t.font, size=t.size, anchor="center",
                                 offset=[0, t.y - 0.5], tracking=t.tracking, width=width, height=height))["box"]
        x, y, w, h = box
        pixels = Image.open(frame["path"]).convert("RGB").crop((round(x * width), round(y * height),
                                                                 round((x + w) * width), round((y + h) * height)))
        behind = "#{:02X}{:02X}{:02X}".format(*pixels.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)))
        colour = t.color[:7]
        if _contrast(colour, behind) < TITLE_CONTRAST:
            out.append(f"title {t.text!r} ({colour}) is hard to read against what's behind it, about {behind} "
                       f"(contrast {_contrast(colour, behind):.1f}, needs {TITLE_CONTRAST:g}): make it lighter or darker, "
                       f"or move it where the set is calmer")
    return out


def _over_pedestal(sb: Storyboard, shot: Shot, title: Title) -> bool:
    """Whether the title's rows cross the pedestal's in the shot: the camera
    centres the product, `fill` of the frame's height, so the pedestal runs
    down from the product's base for `fill` times its height over the
    product's (perspective aside)."""
    if not sb.look.pedestal:
        return False
    top, bottom = _pedestal_rows(sb, shot)
    return title.y - title.size / 2 < bottom and top < title.y + title.size / 2


def _pedestal_rows(sb: Storyboard, shot: Shot) -> tuple[float, float]:
    """The share of the frame's height (0 top) the pedestal covers in the shot."""
    fill = shot.camera.max_fill()
    top = 0.5 + fill / 2
    return top, top + fill * sb.look.pedestal.height / product_size(sb.product)[0]


def shots_from(sb: Storyboard, t: float) -> list[Shot]:
    """The shots on screen from `t` seconds to the end (a title stays on)."""
    return [shot for start, shot in zip(sb.shot_starts(), sb.shots) if t < start + shot.duration] or sb.shots[-1:]


async def title_problems(studio, sb: Storyboard) -> list[str]:
    """Titles that don't fit the frame, overlap each other or the product
    (centred in the frame, `fill` of its height, in every shot from the
    title's start to the end), as the Studio measures them at the ad's frame
    size (placed as build() places them)."""
    width, height = FRAMES[sb.aspect]
    out, boxes = [], []
    for t in sb.titles:
        m = await studio.call("text.measure", text=t.text, font=t.font, size=t.size, anchor="center",
                              offset=[0, t.y - 0.5], tracking=t.tracking, width=width, height=height)
        x, y, w, h = m["box"]
        if not m["fits"]:
            out.append(f"title {t.text!r} doesn't fit the {sb.aspect} frame ({w:.0%} of its width): "
                       f"make it smaller or its tracking tighter")
        for other, (ox, oy, ow, oh) in boxes:
            if y < oy + oh and oy < y + h and x < ox + ow and ox < x + w:
                out.append(f"titles {other!r} and {t.text!r} overlap: move them apart vertically")
        boxes.append((t.text, (x, y, w, h)))
        for shot in shots_from(sb, t.start):
            fill = shot.camera.max_fill()
            top, bottom = 0.5 - 0.5 * fill - TITLE_CLEAR, 0.5 + 0.5 * fill + TITLE_CLEAR
            if y < bottom and top < y + h:
                out.append(f"title {t.text!r} (y {y:.2f} to {y + h:.2f} of the frame) is over the product, which "
                           f"fills {top + TITLE_CLEAR:.2f} to {bottom - TITLE_CLEAR:.2f} in {shot.id} (fill "
                           f"{fill:g}): lower that shot's fill or move the title clear of it")
    return out


def _errors(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]


async def write(brief: str, profile: BrandProfile, *, studio=None, run=None, seconds: float | None = None,
                aspect: str | None = None, tries: int = 3) -> Storyboard:
    """The storyboard for `brief` (its length and frame read from it unless
    given). With a Studio, titles are measured too; with a run, every draft
    and its problems are logged and the result saved as storyboard.json."""
    seconds = seconds or seconds_in(brief) or DEFAULT_SECONDS
    aspect = aspect or aspect_in(brief)
    prompt = PROMPT.format(brief=brief, seconds=seconds, aspect=aspect, profile=_profile_text(profile),
                           styles=_styles_text(), grammar=grammar.load())
    schema = {**Plan.model_json_schema(), "title": "Plan"}
    feedback, found = "", []
    valid = None   # the latest draft that broke only rules of taste: kept if a later one breaks a craft rule
    for attempt in range(1, tries + 1):
        answer = spark.ask(prompt + feedback, schema=schema, system=SYSTEM)
        sb, must = None, []
        try:
            plan = Plan.model_validate(answer.data)
            sb = on_beat(assemble(plan, profile, brief, aspect))
        except ValidationError as e:
            found = must = _errors(e)
        else:
            must = problems(sb, profile, seconds) + (await title_problems(studio, sb) if studio else [])
            found = must + light_problems(sb, profile) + \
                (await title_contrast_problems(studio, sb) + await hero_problems(studio, sb)
                 if studio and not must else [])
        if run:
            run.event("draft", attempt=attempt, problems=found, cached=answer.cached)
        if sb is not None and not must:
            valid = (sb, found)
        if not found or (attempt == tries and valid):
            sb, found = (sb, found) if not found else valid
            if run:
                if found:   # only rules of taste left: the latest such draft kept, with them said
                    run.event("draft_warnings", problems=found)
                run.output("storyboard", run.save_json("storyboard.json", sb))
            return sb
        feedback = ("\n\n# Your previous answer\n\n" + answer.text +
                    "\n\n# What's wrong with it\n\n" + "\n".join(f"- {p}" for p in found) +
                    "\n\nAnswer again with all of these fixed, keeping what was right.")
    raise DirectorError(f"no valid storyboard after {tries} tries: " + "; ".join(found))


if __name__ == "__main__":
    import argparse
    import asyncio
    import sys
    from pathlib import Path

    from pipeline.runs import RUNS, Run
    from pipeline.studio import Studio, build, preview, render

    # Briefs for the brand analyst's three test products (their newest profiles in runs/).
    BRIEFS = {
        "aurelle_perfume": "Luxury perfume ad, dark and moody, 15 seconds.",
        "solana_oil": "Olive oil from a small family grove: warm, natural and honest. 12 seconds.",
        "mira_jar": "Face cream launch for Instagram Reels: clean, calm and bright, vertical, 10 seconds.",
    }

    def profile_of(photo: str) -> BrandProfile:
        found = sorted(RUNS.glob(f"*-analyse-{photo}/brand_profile.json"))
        if not found:
            sys.exit(f"no brand profile for {photo}: run python -m pipeline.agents.analyst first")
        return BrandProfile.model_validate_json(found[-1].read_text(encoding="utf-8"))

    async def main(names: list[str], frames: bool, video: bool, short: int) -> None:
        async with Studio() as studio:
            for name in names:
                profile = profile_of(name)
                with Run.create(f"director-{name}") as run:
                    run.watch(studio)
                    run.event("brief", text=BRIEFS[name], brand=profile.brand)
                    sb = await write(BRIEFS[name], profile, studio=studio, run=run)
                    if frames or video:
                        await build(studio, sb)
                    if frames:
                        await preview(studio, run, sb)
                    if video:
                        await render(studio, run, sb, name, short=short)
                drafts = sum(1 for line in (run.root / "log.jsonl").read_text().splitlines() if '"draft"' in line)
                print(f"\n{name}: {sb.title!r}, style {sb.style}, {sb.aspect}, {sb.duration:g} s, {drafts} draft(s)")
                for start, shot in zip(sb.shot_starts(), sb.shots):
                    print(f"  {start:5.1f}s {shot.id} {shot.camera.move:7} {shot.duration:g}s  {shot.intent}")
                for t in sb.titles:
                    print(f"  title {t.text!r} {t.font} {t.color} at {t.start:g}s, y {t.y:g}")
                print(f"  {Path(run.root).name}")

    parser = argparse.ArgumentParser(description="Storyboards for the test briefs, written by the director; "
                                                 "optionally rendered.")
    parser.add_argument("products", nargs="*", help=f"which (default all): {', '.join(BRIEFS)}")
    parser.add_argument("--preview", action="store_true", help="also render a few frames")
    parser.add_argument("--video", action="store_true", help="also render the video")
    parser.add_argument("--size", type=int, default=1080, help="the video's shorter side in pixels")
    args = parser.parse_args()
    asyncio.run(main(args.products or list(BRIEFS), args.preview, args.video, args.size))
