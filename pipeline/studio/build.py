"""A storyboard into the Studio: the scene, the shots and the titles, as
commands. The hand-made ads and the director both build through this.

    length = await build(studio, storyboard)    # then shot.preview / shot.render up to `length`
"""

from pipeline.catalog.sets import LIGHTS, SURFACES, install_hdri, surface_texture
from pipeline.meta import image
from pipeline.schemas import Product, Storyboard

from . import models
from .client import Studio
from .painted import install_picture

PRODUCT = "product"   # the product entity every shot frames

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}

# Templates' real sizes (height, width) in meters, as product.create makes them (Products.c).
TEMPLATE_SIZES = {"perfume": (0.12, 0.08), "bottle": (0.30, 0.075), "jar": (0.07, 0.09), "can": (0.122, 0.066),
                  "dropper": (0.11, 0.04)}

# Product motion (Shot.motion): each move's default amount, and when a drop has landed (of its shot).
MOTION_AMOUNT = {"turn": 45.0, "float": 0.08, "drop": 0.35, "tilt": 8.0}
DROP_LANDS = 0.4
EDGE = 1e-3   # a shot's last key sits this far before the cut, so the next shot's first key has its own time

# A painted background (Environment.painted): what Muse Image is asked for around the director's place.
PAINT = ("A photograph of {place}, as the background of a premium product photo: an empty place, nothing in the "
         "foreground, no products, no people, no text or logos; eye level, a wide view, natural light and depth.")
PAINT_SIZE = "1536x1024"


TRUCK_ROOM = 0.8   # a truck slides at most this share of the room beside the product (as the Studio's default)


def trucks_in_frame(sb: Storyboard) -> Storyboard:
    """The storyboard with every truck's slide kept within the room beside
    the product, so it stays whole in the frame: a slide given in meters
    can be far more than a long product leaves room for. The room is the
    frame's width at the product (its height over the shot's fill, times
    the frame's aspect) less the product's width."""
    height, width = product_size(sb.product)
    shots = []
    for shot in sb.shots:
        camera = shot.camera
        if camera.move == "truck" and camera.travel is not None:
            frame_width = height / max(camera.fill, 1e-3) * ASPECTS[sb.aspect]
            room = TRUCK_ROOM * max(frame_width - width, 0.0)
            if abs(camera.travel) > room:
                camera = camera.model_copy(update={"travel": round(room if camera.travel > 0 else -room, 4)})
        shots.append(shot.model_copy(update={"camera": camera}))
    return sb.model_copy(update={"shots": shots})


def product_size(product: Product) -> tuple[float, float]:
    """The product's height and width in meters, as the Studio builds it."""
    if product.model:
        return models.size(product.model)
    if product.profile_parts:
        points = [pt for part in product.profile_parts for pt in part.profile]
        return max(y for _, y in points), 2 * max(r for r, _ in points)
    height, width = TEMPLATE_SIZES[product.template]
    return product.height or height, product.width or width


def _clean(model) -> dict:
    """A model as command arguments: aliases ("from"), no unset values."""
    return model.model_dump(by_alias=True, exclude_none=True)


def _surfaced(model) -> dict:
    """A backdrop or pedestal as backdrop.create's arguments: a library
    surface becomes its texture (white, so the texture's own colours show),
    tiled and as rough as the material is."""
    args = _clean(model)
    surface = args.pop("surface", None)
    if surface:
        _, roughness, tile, _ = SURFACES[surface]
        args.update(texture=str(surface_texture(surface).resolve()), texture_tile=tile, roughness=roughness,
                    color="#FFFFFF")
    return args


async def build_scene(studio: Studio, sb: Storyboard) -> dict:
    """Environment, backdrop, pedestal, product and lights (the light
    environment and surfaces from the set library, by name). Returns the
    lights' intensities by entity."""
    look = sb.look
    await studio.call("studio.reset")
    environment = _clean(look.environment)
    painted = environment.pop("painted", None)
    if painted:                          # Muse Image paints it; made a light environment (pipeline.studio.painted)
        picture = image.generate(PAINT.format(place=painted), size=PAINT_SIZE)
        environment["hdri"] = install_picture(studio, picture)
    elif environment["hdri"] in LIGHTS:  # a light environment by name: installed into the Studio's assets
        environment["hdri"] = install_hdri(studio, environment["hdri"])
    await studio.call("environment.set", **environment)
    await studio.call("render.set", antialiasing="taa", clear_color=look.background)

    if look.backdrop:
        await studio.call("backdrop.create", kind="cyclorama", **_surfaced(look.backdrop))
    top = 0.0
    if look.pedestal:
        await studio.call("backdrop.create", kind="pedestal", **_surfaced(look.pedestal))
        top = look.pedestal.height

    product = sb.product
    if product.model:
        await place_product_model(studio, product, top)
    else:
        await create_product(studio, product, top)

    lighting = look.lighting
    glow = {k: v for k, v in (("glow", lighting.glow), ("glow_color", lighting.glow_color)) if v is not None}
    lights = await studio.call("lighting.preset", subject=PRODUCT, name=lighting.preset, intensity=lighting.intensity,
                               turn=lighting.turn, warmth=lighting.warmth, **glow)
    return {light["entity"]: light["intensity"] for light in lights["lights"]}


async def create_product(studio: Studio, product: Product, top: float) -> None:
    """A product spun from a profile (a template or the analyst's traced
    parts), standing at the origin on the pedestal's top."""
    args = {"name": PRODUCT, "position": [0, top, 0]}
    if product.template:
        args["template"] = product.template
        args["parts"] = {name: _clean(part) for name, part in product.parts.items()}
    else:
        args["parts"] = [_clean(part) for part in product.profile_parts]
    for key in ("height", "width"):
        if getattr(product, key) is not None:
            args[key] = getattr(product, key)
    if product.label:
        args["label"] = _clean(product.label)
    await studio.call("product.create", **args)


# The finish fields place_model takes as overrides of a model's material; its
# colours stay its texture's.
MODEL_FINISH = ("metallic", "roughness", "transmission", "ior", "thickness")


async def place_product_model(studio: Studio, product: Product, top: float) -> None:
    """A product as a 3D model file (any shape: pipeline.studio.models),
    installed into the Studio's assets and stood at the origin on the
    pedestal's top, in its own size (normalized to meters), with its finish."""
    key = models.install(studio, product.model)
    args = {"model": key, "name": PRODUCT, "position": [0, top, 0], "scale": [1, 1, 1]}
    if product.finish:
        finish = {k: v for k, v in _clean(product.finish).items() if k in MODEL_FINISH}
        if finish:
            args["material"] = finish
    await studio.call("place_model", **args)


async def add_titles(studio: Studio, sb: Storyboard) -> None:
    """Each title starts hidden and at its `start` fades in over `fade`
    seconds while rising 2% of the frame and drawing its letters together."""
    for i, t in enumerate(sb.titles):
        name = f"title_{i}"
        await studio.call("text.create", name=name, text=t.text, font=t.font, size=t.size, anchor="center",
                          offset=[0, t.y - 0.5], color=t.color, tracking=t.tracking, opacity=0)
        end = t.start + t.fade + 0.3
        for field, a, b in (("opacity", 0, 1), ("offset", [0, t.y - 0.48], [0, t.y - 0.5]),
                            ("tracking", t.tracking + 0.15, t.tracking)):
            await studio.call("timeline.set_track", entity=name, component="Text", field=field,
                              keys=[{"t": t.start, "value": a, "ease": "out"}, {"t": end, "value": b}])


async def build(studio: Studio, sb: Storyboard) -> float:
    """The whole storyboard; returns the ad's length in seconds."""
    lights = await build_scene(studio, sb)

    aspect = ASPECTS[sb.aspect]
    for start, shot in zip(sb.shot_starts(), sb.shots):
        await studio.call("camera.move", subject=PRODUCT, start=start, duration=shot.duration, aspect=aspect,
                          **_clean(shot.camera))

    if sb.look.lighting.fade_in:
        for light, intensity in lights.items():
            await studio.call("timeline.set_track", entity=light, component="Light", field="intensity",
                              keys=[{"t": 0, "value": 0.0, "ease": "in"},
                                    {"t": sb.look.lighting.fade_in, "value": intensity}])
    for track in sb.tracks:
        await studio.call("timeline.set_track", **_clean(track))
    await add_motion(studio, sb)
    await add_titles(studio, sb)
    return sb.duration


def motion_keys(sb: Storyboard) -> dict[str, list[dict]]:
    """The product's Transform keys for its shots' motion, by field
    ("position", "rotation_deg"): each shot moves from its own start and the
    product is back at rest at the next cut (a step key just before it);
    shots without motion hold it at rest. Only fields some shot moves."""
    top = sb.look.pedestal.height if sb.look.pedestal else 0.0
    height = product_size(sb.product)[0]
    rest = {"position": [0.0, top, 0.0], "rotation_deg": [0.0, 0.0, 0.0]}
    keys: dict[str, list[dict]] = {"position": [], "rotation_deg": []}
    for start, shot in zip(sb.shot_starts(), sb.shots):
        end = start + shot.duration - EDGE
        m = shot.motion
        amount = (m.amount if m.amount is not None else MOTION_AMOUNT[m.move]) if m else 0.0
        moves = {}
        if m and m.move == "turn":     # from `amount` degrees round back to facing front
            moves["rotation_deg"] = [(start, [0.0, -amount, 0.0], "out"), (end, [0.0, 0.0, 0.0], "step")]
        elif m and m.move == "tilt":   # leans towards the camera (+Z) and back
            moves["rotation_deg"] = [(start, [0.0, 0.0, 0.0], "in_out"),
                                     ((start + end) / 2, [amount, 0.0, 0.0], "in_out"), (end, [0.0, 0.0, 0.0], "step")]
        elif m and m.move == "float":  # rises, eased, through the shot
            moves["position"] = [(start, [0.0, top, 0.0], "in_out"), (end, [0.0, top + amount * height, 0.0], "step")]
        elif m and m.move == "drop":   # falls, accelerating, and lands
            moves["position"] = [(start, [0.0, top + amount * height, 0.0], "in"),
                                 (start + DROP_LANDS * shot.duration, [0.0, top, 0.0], "step")]
        for field in keys:
            keys[field] += [{"t": round(t, 4), "value": v, "ease": e} for t, v, e in moves.get(field, [])] \
                or [{"t": round(start, 4), "value": rest[field], "ease": "step"}]
    return {field: k for field, k in keys.items() if any(k_["value"] != rest[field] for k_ in k)}


async def add_motion(studio: Studio, sb: Storyboard) -> None:
    """The shots' product motion (Shot.motion), as tracks on the product's
    Transform; a field the storyboard's own tracks already animate is left
    to them."""
    taken = {t.field for t in sb.tracks if t.entity == PRODUCT and t.component == "Transform"}
    for field, keys in motion_keys(sb).items():
        if field not in taken:
            await studio.call("timeline.set_track", entity=PRODUCT, component="Transform", field=field, keys=keys)
