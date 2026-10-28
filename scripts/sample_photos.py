"""Product photos of fictional brands, made with Muse Image, for testing the
brand analyst: Assets/photos/<name>.png. Cached, so rerunning costs nothing.

    .venv\\Scripts\\python scripts\\sample_photos.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.meta import image, usage  # noqa: E402

OUT = ROOT / "Assets" / "photos"

STYLE = ("Studio product photograph, straight-on front view at eye level, the whole product upright and "
         "centered with space around it, plain light grey seamless background, soft even light, sharp focus, "
         "no hands, no props, no other objects.")

PHOTOS = {
    "aurelle_perfume": "A luxury perfume bottle: thick clear glass with amber perfume, a tall round gold metal cap, "
                       "a small cream label on the front with the brand name 'AURELLE' in an elegant serif.",
    "solana_oil": "A tall dark green glass olive oil bottle with a round body, long neck and a black screw cap, "
                  "a wide white paper label with 'SOLANA' in large black letters and 'extra virgin olive oil' below.",
    "mira_jar": "A short wide white ceramic skincare cream jar with a brushed silver lid, a pale pink label "
                "around it with 'MIRA' in thin sans-serif capitals.",
}


def main() -> None:
    for name, prompt in PHOTOS.items():
        path = image.generate(f"{prompt} {STYLE}", size="1024x1536", out=OUT / f"{name}.png")
        print(path)
    print(usage.summary()["cost"], "dollars")


if __name__ == "__main__":
    main()
