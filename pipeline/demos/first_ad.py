"""The first ad, now the "noctis" spec in pipeline/demos/ads.py; kept so
this command still works.

    python -m pipeline.demos.first_ad              # pipeline/demos/out/noctis.mp4
    python -m pipeline.demos.first_ad --preview    # a few frames as PNGs
"""

import argparse
import asyncio

from pipeline.demos.ads import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true", help="a few frames as PNGs instead of the video")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=16)
    args = parser.parse_args()
    asyncio.run(run(["noctis"], args.preview, args.width, args.height, args.samples))
