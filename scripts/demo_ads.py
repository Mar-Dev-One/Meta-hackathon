"""Makes the demo ads: the eight fictional brands, each from its Muse Image
photo in Assets/photos/ and a brief, one after the other, each a run in
runs/ (open them in the app; the gallery shows them all).

    python scripts/demo_ads.py                  # all eight
    python scripts/demo_ads.py stride volt      # just these (by the photo's first word)
    python scripts/demo_ads.py --list           # what it would make

Every brand is made up and every photo made by Muse Image; the sets are
CC0 and the 3D models CC0 or CC-BY, credited in each run's model_credit.json.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# photo, category, format, brief
ADS = [
    ("aurelle_perfume.png", "perfume bottle", "both",
     "Luxury perfume ad, timeless and elegant, warm and intimate, 15 seconds."),
    ("mira_jar.png", "cream jar", "both",
     "Face cream ad: a calm spa morning, soft light, serene and fresh, 12 seconds."),
    ("stride_sneaker.png", "running shoe", "both",
     "Running shoe launch ad: energetic, fast and sporty, full of motion, 12 seconds."),
    ("solana_oil.png", "olive oil bottle", "horizontal",
     "Olive oil from a Mediterranean family kitchen: sunlit, warm, generous and honest, 12 seconds."),
    ("brew_mug.png", "coffee mug", "horizontal",
     "Ceramic mug ad: cosy, slow Sunday morning, warm and handmade, 12 seconds."),
    ("volt_controller.png", "game controller", "horizontal",
     "Game controller launch ad: bold, neon and electric, made for gamers, 12 seconds."),
    ("nova_headphones.png", "over-ear headphones", "horizontal",
     "Wireless headphones ad: sleek, premium and minimal, in a dark studio, 15 seconds."),
    ("orbit_watch.png", "wristwatch", "horizontal",
     "Watch ad: refined and timeless, 12 seconds."),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Make the demo ads, one run each.")
    parser.add_argument("only", nargs="*", help="just these, by the photo's first word (aurelle, mira, ...)")
    parser.add_argument("--list", action="store_true", help="say what it would make, and stop")
    args = parser.parse_args()
    chosen = [a for a in ADS if not args.only or a[0].split("_")[0] in args.only]
    for photo, category, format, brief in chosen:
        print(f"{photo}: {format}, {category}: {brief}")
    if args.list:
        return
    failed = []
    for photo, category, format, brief in chosen:
        began = time.time()
        print(f"\n=== {photo} ===", flush=True)
        made = subprocess.run([sys.executable, "-m", "pipeline.agents.producer", str(ROOT / "Assets" / "photos" / photo),
                               brief, "--category", category, "--format", format], cwd=ROOT)
        print(f"=== {photo}: {'done' if made.returncode == 0 else 'FAILED'} in {time.time() - began:.0f} s ===", flush=True)
        if made.returncode:
            failed.append(photo)
    print(f"\n{len(chosen) - len(failed)} of {len(chosen)} made" + (f"; failed: {', '.join(failed)}" if failed else ""))


if __name__ == "__main__":
    main()
