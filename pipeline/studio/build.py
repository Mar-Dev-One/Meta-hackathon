"""A storyboard into the Studio: the scene, the shots and the titles, as
commands. The hand-made ads and the director both build through this.

    length = await build(studio, storyboard)    # then shot.preview / shot.render up to `length`
"""

from pipeline.schemas import Storyboard

from .client import Studio

PRODUCT = "product"   # the product entity every shot frames

ASPECTS = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}


def _clean(model) -> dict:
    """A model as command arguments: aliases ("from"), no unset values."""
    return model.model_dump(by_alias=True, exclude_none=True)


async def build_scene(studio: Studio, sb: Storyboard) -> dict:
    """Environment, backdrop, pedestal, product and lights. Returns the
    lights' intensities by entity."""
    look = sb.look
    await studio.call("studio.reset")
    await studio.call("environment.set", **_clean(look.environment))
    await studio.call("render.set", antialiasing="taa", clear_color=look.background)

    await studio.call("backdrop.create", kind="cyclorama", **_clean(look.backdrop))
    top = 0.0
    if look.pedestal:
        await studio.call("backdrop.create", kind="pedestal", **_clean(look.pedestal))
        top = look.pedestal.height

    product = sb.product
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

    lighting = look.lighting
    glow = {k: v for k, v in (("glow", lighting.glow), ("glow_color", lighting.glow_color)) if v is not None}
    lights = await studio.call("lighting.preset", subject=PRODUCT, name=lighting.preset, intensity=lighting.intensity,
                               turn=lighting.turn, warmth=lighting.warmth, **glow)
    return {light["entity"]: light["intensity"] for light in lights["lights"]}


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
    await add_titles(studio, sb)
    return sb.duration
