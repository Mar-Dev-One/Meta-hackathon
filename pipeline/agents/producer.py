"""The whole chain: a product photo and a brief in, a finished ad out, as
one run (runs/<time>-ad-<photo>/).

    with Run.create("ad-aurelle") as run:
        videos = await make_ad(studio, run, "Luxury perfume ad, dark and moody, 15 seconds.", photo)

The brand analyst reads the photo (brand_profile.json, masks, label), the
director plans the ad (storyboard.json), the critic loop judges and revises
it until every shot and the whole ad pass (rounds/, critiques/; at most 3
revisions, the best kept), and the video is rendered and finished (final/),
with music: horizontal (16:9), vertical (9:16), or both from the same
storyboard (the default).

    python -m pipeline.agents.producer Assets/photos/aurelle_perfume.png "Luxury perfume ad, dark and moody, 15 seconds." --category "perfume bottle"
    python -m pipeline.agents.producer Assets/photos/mira_jar.png "Face cream, calm and bright, 10 seconds." --category "cream jar" --format vertical
"""

from pathlib import Path

from pipeline.runs import Run
from pipeline.schemas import BrandProfile
from pipeline.studio import build, final_cut, models, preview

from .analyst import analyse
from .critic.loop import refine
from .director.write import write
from .scout import scout
from .stager import stage


# The ad's format: one frame, planned and judged in it, or both (the brief's
# frame planned and judged, the other reframed from it).
FORMATS = {"horizontal": "16:9", "vertical": "9:16", "both": None}


async def make_ad(studio, run: Run, brief: str, photo: Path | str, category: str = "product", short: int = 1080,
                  video: bool = True, critic: bool = True, format: str = "both", model: Path | str | None = None,
                  credit: dict | None = None) -> dict[str, Path] | None:
    """The ad for `brief` with the product in `photo`: its videos by aspect
    (None with video=False). `format` is "horizontal" (16:9), "vertical"
    (9:16) or "both": the director plans for the chosen frame, or, for both,
    the brief's (vertical if it says so) and the other is reframed from it.
    `model` is a 3D model file (.glb) of the product, for shapes that aren't
    round (`credit` is its candidate's, kept in the run as model_credit.json);
    without one, the scout looks at the photo: a round product is traced from
    it, any other shape gets the closest model found online, if one fits.
    Without the critic, the director's first storyboard is built and a few
    frames previewed (frames/)."""
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}, not {format!r}")
    run.watch(studio)
    run.event("brief", text=brief, photo=Path(photo).name, category=category, format=format,
              model=Path(model).name if model else None)
    analysis = analyse(run, photo, category)
    box = analysis.seg.product.box
    aspect = (box[3] - box[1]) / max(box[2] - box[0], 1)   # the product's outline in the photo, height / width
    if not model:
        model, credit = scout(run, photo, analysis.profile.category)
    if model:
        profile = await with_model(studio, run, analysis.profile, model, credit, photo, analysis.profile.category,
                                   aspect)
    else:
        profile = analysis.profile
    sb = await write(brief, profile, studio=studio, run=run, aspect=FORMATS[format])
    if critic:
        sb, _ = await refine(studio, sb, profile, run)
    else:
        await build(studio, sb)
        await preview(studio, run, sb)
    if not video:
        return None
    aspects = (sb.aspect,) + (tuple(a for a in ("16:9", "9:16") if a != sb.aspect) if format == "both" else ())
    return await final_cut(studio, run, sb, Path(photo).stem, aspects=aspects, short=short)


async def with_model(studio, run: Run, profile: BrandProfile, model: Path | str, credit: dict | None,
                     photo: Path | str, category: str = "product", aspect: float | None = None) -> BrandProfile:
    """The brand profile with `model` as its product (run's product.glb):
    stood and turned the way Muse Spark sees the product in `photo` (the
    stager; the photo's `aspect` if it can't answer), fitted to its real
    height, and dressed in the analyst's materials part by part, in place of
    the traced shape and the label (a label can't be wrapped onto any
    shape). Saved again as brand_profile.json; the model's credit as
    model_credit.json."""
    up, turn = await stage(studio, run, model, photo, profile.height, category=category, aspect=aspect)
    parts = {m.name: m.surface() for m in profile.materials}
    fitted = models.fit(model, run.path("product.glb"), height=profile.height, parts=parts, up=up, turn=turn)
    height, width = models.size(fitted)
    profile = profile.model_copy(update={"model": str(fitted), "profile_parts": None, "template": None, "label": None})
    run.output("brand_profile", run.save_json("brand_profile.json", profile))
    if credit:
        run.output("model_credit", run.save_json("model_credit.json", credit))
    run.event("model_fitted", file="product.glb", height=round(height, 4), width=round(width, 4),
              source=(credit or {}).get("source", "upload"), name=(credit or {}).get("name"),
              credit=(credit or {}).get("credit"))
    return profile


if __name__ == "__main__":
    import argparse
    import asyncio
    import json
    import time

    from pipeline.studio import Studio

    parser = argparse.ArgumentParser(description="A product photo and a brief in, a finished ad out (one run).")
    parser.add_argument("photo")
    parser.add_argument("brief")
    parser.add_argument("--category", default="product", help='what the product is, e.g. "perfume bottle"')
    parser.add_argument("--size", type=int, default=1080, help="the video's shorter side in pixels")
    parser.add_argument("--preview", action="store_true", help="no video: stop once the storyboard is final")
    parser.add_argument("--no-critic", action="store_true", help="render the director's first storyboard as it is")
    parser.add_argument("--format", choices=list(FORMATS), default="both",
                        help="horizontal (16:9), vertical (9:16) or both (default)")
    parser.add_argument("--model", help="a 3D model file (.glb) of the product, for shapes that aren't round")
    args = parser.parse_args()

    async def main() -> None:
        began = time.time()
        async with Studio() as studio:
            with Run.create(f"ad-{Path(args.photo).stem}") as run:
                videos = await make_ad(studio, run, args.brief, args.photo, args.category, args.size,
                                       video=not args.preview, critic=not args.no_critic, format=args.format,
                                       model=args.model)
        summary = json.loads((run.root / "run.json").read_text(encoding="utf-8"))
        made = "\n".join(str(v) for v in videos.values()) if videos else str(run.root)
        print(f"{made}\n{time.time() - began:.0f} s, {summary['model_calls']} model calls "
              f"({summary['cached_calls']} cached), ${summary['cost']:.4f}")

    asyncio.run(main())
