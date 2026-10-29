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
"""

from pipeline.schemas import Storyboard

from .build import ASPECTS
from .render import frame_size

TITLE_WIDTH = 0.88     # of the frame's width, at most, for a title's box


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
    return sb.model_copy(update={"aspect": aspect, "titles": titles, "shots": shots})
