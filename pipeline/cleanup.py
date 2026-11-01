"""What piles up, cleared: files made along the way that are made again
when they're needed. It says what it would remove; --yes removes it.

    python -m pipeline.cleanup                 # what would go, and how much
    python -m pipeline.cleanup --yes           # gone (no Studio may be running: it uses the assets)
    python -m pipeline.cleanup --yes --days 0  # everything, however recent

Cleared, if older than --days (default 1, so a run under way keeps its own):
- the Studio's generated meshes (products/product_*, pedestal_*, backdrop_*:
  written again when a scene needs them), the models copied in for scenes
  (products/model_*.glb: copied again from wherever they live) and painted
  backgrounds (hdri/painted_*.hdr: copied again from cache/painted). The
  set library's light environments and the Studio's own assets stay.
- the frames rendered to check titles and the hero (cache/title_check).
- in runs: the model files used only on the way (the stager's ways up, the
  render pick's finalists, the colourist's versions, a final render's raw
  video before its sound and end card). Each run's product.glb (its
  storyboard points at it), its videos, sheets, frames, JSON and log stay:
  every run still opens, and can be made again (pipeline.runs.inputs).
"""

import argparse
import time
from pathlib import Path

from pipeline.meta.config import ROOT
from pipeline.runs import RUNS

ASSETS = ROOT / "build" / "Release" / "assets"
GENERATED = ("products/product_*", "products/pedestal_*", "products/backdrop_*", "products/model_*.glb",
             "hdri/painted_*.hdr")
CHECKS = ROOT / "cache" / "title_check"
ON_THE_WAY = ("stage/**/*.glb", "colour/**/*.glb", "final/raw*.mp4")


def leftovers(days: float = 1.0) -> list[Path]:
    """Every file `cleanup` would remove: made along the way, older than `days`."""
    before = time.time() - days * 86400
    found = [f for pattern in GENERATED for f in ASSETS.glob(pattern)]
    found += [f for f in CHECKS.rglob("*") if f.is_file()]
    for run in RUNS.iterdir() if RUNS.exists() else []:
        if run.is_dir():
            found += [f for pattern in ON_THE_WAY for f in run.glob(pattern)]
    return sorted(f for f in found if f.is_file() and f.stat().st_mtime < before)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear files made along the way (they're made again when needed).")
    parser.add_argument("--yes", action="store_true", help="remove them (without it: only say what would go)")
    parser.add_argument("--days", type=float, default=1.0, help="only files older than this many days (default 1)")
    args = parser.parse_args()
    files = leftovers(args.days)
    size = sum(f.stat().st_size for f in files)
    groups: dict[str, list[Path]] = {}
    for f in files:
        top = f.relative_to(ROOT).parts
        groups.setdefault("runs" if top[0] == "runs" else "/".join(top[:-1]), []).append(f)
    for name, members in sorted(groups.items()):
        print(f"{name}: {len(members)} files, {sum(f.stat().st_size for f in members) / 2**20:.0f} MB")
    if not args.yes:
        print(f"{len(files)} files, {size / 2**20:.0f} MB would go; --yes removes them")
        return
    for f in files:
        f.unlink(missing_ok=True)
    print(f"removed {len(files)} files, {size / 2**20:.0f} MB")


if __name__ == "__main__":
    main()
