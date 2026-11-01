"""A storyboard in another frame: the same ad, 9:16 for social or 1:1.

    vertical = await reframe(studio, sb, "9:16")

The framing needs nothing: camera.move frames for the frame's shape (`fill`
is a share of its height; the width may take up to 80% of a narrow frame),
so a tall bottle sits as it did and a squat jar is held by the width. A
truck's slide is in meters, so one written into the storyboard is scaled by
how much narrower the frame is (its default already is), or it slides the
product out of a 9:16 frame. Titles' size is a share of the frame's height,
so a name sized for 16:9 can be wider than a 9:16 frame: each is measured
by the Studio in the new frame and shrunk, if it must be, to fit within
TITLE_WIDTH of its width.

A wide product (a shoe, a controller) in a narrow frame is held by the
width: every shot ended up the same, the product edge to edge, whatever its
`fill`. So in a narrow frame each shot's product is measured (shot.bounds)
and the shots' fills are scaled by one factor, so the widest spans
WIDE_SHARE of the width and the others keep their sizes relative to it (a
wide shot still wider than a medium one). Close-ups (fill over CLOSE) crop
on purpose and keep theirs.
"""

from pipeline.schemas import Storyboard

from .build import ASPECTS, PRODUCT, build
from .render import frame_size

TITLE_WIDTH = 0.88     # of the frame's width, at most, for a title's box
WIDE_SHARE = 0.68      # of a narrow frame's width, at most, for the product in its widest shot (not a close-up)
CLOSE = 0.7            # a fill over this is a close-up: its sides may crop (camera.move's FRAMING_CLOSE)


async def reframe(studio, sb: Storyboard, aspect: str) -> Storyboard:
    """`sb` in `aspect` ("16:9", "9:16", "1:1"), its titles fitted."""
    if aspect == sb.aspect:
        return sb
    width, height = frame_size(aspect, 1080)
    titles = []
    for t in sb.titles:
        box = (await studio.call("text.measure", text=t.text, font=t.font, size=t.size, anchor="center",
                                 offset=[0, t.y - 0.5], tracking=t.tracking, width=width, height=height))["box"]
        if box[2] > TITLE_WIDTH:
            t = t.model_copy(update={"size": round(t.size * TITLE_WIDTH / box[2], 4)})
        titles.append(t)
    narrower = min(1.0, ASPECTS[aspect] / ASPECTS[sb.aspect])
    shots = [s.model_copy(update={"camera": s.camera.model_copy(update={"travel": round(s.camera.travel * narrower, 4)})})
             if s.camera.move == "truck" and s.camera.travel is not None else s for s in sb.shots]
    framed = sb.model_copy(update={"aspect": aspect, "titles": titles, "shots": shots})
    return await roomier(studio, framed) if ASPECTS[aspect] < 1 else framed


async def _widest(studio, sb: Storyboard) -> float:
    """The most of the frame's width the product spans in any shot but a
    close-up: at each shot's start, middle and end, as built."""
    width, height = frame_size(sb.aspect, 1080)
    await build(studio, sb)
    widest = 0.0
    for start, shot in zip(sb.shot_starts(), sb.shots):
        if shot.camera.max_fill() > CLOSE:
            continue
        for t in (start + 0.02, start + shot.duration / 2, start + shot.duration - 0.05):
            box = (await studio.call("shot.bounds", entity=PRODUCT, t=t, width=width, height=height)).get("box")
            if box:
                widest = max(widest, box[2] - box[0])
    return widest


def _scaled(sb: Storyboard, factor: float) -> Storyboard:
    """`sb` with every shot's fills but a close-up's times `factor`."""
    def camera(c):
        update = {k: max(0.05, round(getattr(c, k) * factor, 4)) for k in ("fill", "from_fill", "to_fill")
                  if getattr(c, k) is not None}
        if c.points:   # a path's framing is its waypoints'
            update["points"] = [p.model_copy(update={"fill": max(0.05, round(p.fill * factor, 4))}) for p in c.points]
        return c.model_copy(update=update)
    return sb.model_copy(update={"shots": [s if s.camera.max_fill() > CLOSE else s.model_copy(update={"camera": camera(s.camera)})
                                           for s in sb.shots]})


async def roomier(studio, sb: Storyboard, rounds: int = 4) -> Storyboard:
    """`sb` (a narrow frame) with its shots' fills scaled by one factor so
    the product spans WIDE_SHARE of the width in the widest of them,
    close-ups left as they are; unchanged if it already spans no more. Found
    by measuring: once no shot is held by the width, its span follows its
    fill, so a few rounds settle (one held by the width spans more than its
    fill says, so the first is a guess)."""
    widest = await _widest(studio, sb)
    if widest <= WIDE_SHARE + 0.02:
        return sb
    factor, best = WIDE_SHARE / widest, None
    for _ in range(rounds):
        trial = _scaled(sb, factor)
        span = await _widest(studio, trial)
        if span <= WIDE_SHARE + 0.02 and (best is None or span > best[0]):
            best = (span, trial)
        if abs(span - WIDE_SHARE) <= 0.02 or not span:
            break
        factor *= WIDE_SHARE / span
    return best[1] if best else _scaled(sb, factor)
