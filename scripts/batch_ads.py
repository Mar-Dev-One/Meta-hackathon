"""A batch of ads for 30 new products, 15 seconds to 2 minutes long: each
product's photo made by Muse Image (fictional brands, Assets/photos/batch/,
made once), then its ad, one after the other, horizontal. A failure is
logged and the batch carries on. Made to run unattended (overnight: about
8-10 hours); a summary is written to runs/batch_summary.txt as it goes.

    python scripts/batch_ads.py              # all 30
    python scripts/batch_ads.py --photos     # only the photos
    python scripts/batch_ads.py kova halo    # just these
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.meta import image  # noqa: E402

PHOTOS = ROOT / "Assets" / "photos" / "batch"
SUMMARY = ROOT / "runs" / "batch_summary.txt"

STYLE = ("Studio product photograph, straight-on front view at eye level, the whole product centered with space "
         "around it, plain light grey seamless background, soft even light, sharp focus, no hands, no props, no "
         "other objects.")

# name, what it is (for the photo), category, brief
ADS = [
    ("lumen_candle", "A scented candle in a short amber glass jar with a wooden lid, a small kraft label reading 'LUMEN'.",
     "scented candle", "Scented candle ad: cosy, calm, a quiet evening at home, 15 seconds."),
    ("marea_bottle", "A matte navy stainless steel water bottle with a silver screw cap, 'MAREA' engraved on it.",
     "water bottle", "Reusable water bottle ad: fresh, active, outdoors, 20 seconds."),
    ("kova_kettle", "A modern matte white electric kettle with a curved handle and a small light-wood base, 'KOVA' on its side.",
     "electric kettle", "Electric kettle ad: Scandinavian, clean and calm, a slow morning ritual, 30 seconds."),
    ("scarla_lipstick", "An open lipstick in a slim gold metal case, the lipstick deep red, 'SCARLA' on the case.",
     "lipstick", "Lipstick launch ad: bold, glamorous, confident, 15 seconds."),
    ("noir_sunglasses", "A pair of black acetate sunglasses with dark lenses, folded open, 'NOIR' on the arm.",
     "sunglasses", "Sunglasses ad: cool, summer, effortless style, 45 seconds."),
    ("aero_drone", "A compact white quadcopter camera drone with four rotors and a small camera underneath, 'AERO' on top.",
     "camera drone", "Camera drone launch ad: adventurous, high-tech, sweeping, 1 minute."),
    ("pulse_speaker", "A small cylindrical smart speaker covered in grey fabric with a glowing ring on top, 'PULSE' on the base.",
     "smart speaker", "Smart speaker ad: modern home, warm and friendly, 30 seconds."),
    ("haven_backpack", "A rugged olive green canvas backpack with brown leather straps and buckles, 'HAVEN' on a leather tag.",
     "backpack", "Backpack ad: travel, adventure, made to last, 45 seconds."),
    ("frost_icecream", "A pint tub of ice cream with a pastel pink lid and a white tub printed with strawberries, 'FROST' on it.",
     "ice cream tub", "Ice cream ad: playful, sweet, summery, 20 seconds."),
    ("pura_toothpaste", "A toothpaste tube standing on its cap, white with a mint green band, 'PURA MINT' on it.",
     "toothpaste tube", "Toothpaste ad: fresh, clean, bright, 15 seconds."),
    ("velvet_polish", "A small square glass bottle of glossy burgundy nail polish with a tall black cap, 'VELVET' on it.",
     "nail polish bottle", "Nail polish ad: chic, elegant, a touch of luxury, 20 seconds."),
    ("glow_lamp", "A modern desk lamp with a round white base, a thin brass arm and a dome shade, 'GLOW' on the base.",
     "desk lamp", "Desk lamp ad: design object, warm light, a creative workspace at night, 1 minute."),
    ("drift_skateboard", "A skateboard deck with a bold orange and purple graphic, black wheels, 'DRIFT' across the deck.",
     "skateboard", "Skateboard ad: urban, energetic, rebellious, 45 seconds."),
    ("breva_espresso", "A compact brushed steel espresso machine with a black portafilter and a small cup, 'BREVA' on the front.",
     "espresso machine", "Espresso machine ad: Italian craft, rich and sensual, the perfect shot, 90 seconds."),
    ("snappa_camera", "A retro instant camera in mint green and white with a big round lens, 'SNAPPA' above the lens.",
     "instant camera", "Instant camera ad: nostalgic, fun, friends and memories, 1 minute."),
    ("mono_keyboard", "A compact mechanical keyboard with cream and grey keycaps and an orange escape key, 'MONO' on a key.",
     "mechanical keyboard", "Mechanical keyboard ad: precise, satisfying, made for creators, 45 seconds."),
    ("ripple_honey", "A hexagonal glass jar of golden honey with a wooden dipper on its lid, 'RIPPLE' on a paper label.",
     "honey jar", "Honey ad: natural, golden, from the hive to your table, 30 seconds."),
    ("sable_wallet", "A slim folded wallet in rich brown leather with visible stitching, 'SABLE' embossed on it.",
     "leather wallet", "Leather wallet ad: crafted, timeless, quiet luxury, 30 seconds."),
    ("bolt_energy", "A tall slim drink can in electric blue with a lightning bolt and 'BOLT' in white.",
     "energy drink can", "Energy drink ad: loud, fast, extreme, 15 seconds."),
    ("grove_tea", "A round metal tea tin in sage green with a gold lid and a botanical pattern, 'GROVE' on it.",
     "tea tin", "Tea ad: serene, botanical, a mindful moment, 30 seconds."),
    ("zest_lemonade", "A clear glass bottle of cloudy yellow lemonade with a swing-top cap, 'ZEST' on a white label.",
     "lemonade bottle", "Lemonade ad: sunny, refreshing, summer afternoon, 20 seconds."),
    ("halo_helmet", "A sleek matte white bicycle helmet with vents and a reflective strip, 'HALO' on the side.",
     "bicycle helmet", "Bicycle helmet ad: safe, sleek, the city on two wheels, 1 minute."),
    ("spark_toothbrush", "An electric toothbrush in white and teal standing upright on its charger, 'SPARK' on the handle.",
     "electric toothbrush", "Electric toothbrush ad: clean, modern, confident smile, 30 seconds."),
    ("cove_sunscreen", "A sunscreen tube in coral and white standing on its cap, 'COVE SPF 50' on it.",
     "sunscreen tube", "Sunscreen ad: beach, sun, carefree summer, 30 seconds."),
    ("forge_knife", "A chef's knife with a long damascus steel blade and a dark wooden handle, 'FORGE' etched on the blade.",
     "chef knife", "Chef knife ad: craftsmanship, precision, the art of cooking, 45 seconds."),
    ("tempo_earbuds", "An open wireless earbuds charging case in glossy black with two earbuds inside, 'TEMPO' on the lid.",
     "wireless earbuds", "Wireless earbuds launch ad: music, motion, urban nights, 30 seconds."),
    ("pebble_mouse", "A smooth rounded wireless mouse in soft grey, 'PEBBLE' in small letters on top.",
     "computer mouse", "Wireless mouse ad: minimal, smooth, effortless work, 20 seconds."),
    ("lyra_guitar", "An acoustic guitar with a natural spruce top, a dark rosewood body and a round sound hole, 'LYRA' on the headstock.",
     "acoustic guitar", "Acoustic guitar ad: warm, soulful, the sound of craftsmanship, a story in parts, 2 minutes."),
    ("quill_pen", "A black lacquered fountain pen with gold trim and its cap posted, 'QUILL' engraved on the clip.",
     "fountain pen", "Fountain pen ad: elegant, literary, the art of writing, 90 seconds."),
    ("rally_car", "A detailed 1:18 scale model of a red vintage rally car with white racing stripes and the number 7, 'RALLY' on the doors.",
     "model car", "Collectible model car ad: nostalgic, cinematic, the thrill of the race, 2 minutes."),
]


def photo(name: str, what: str) -> Path:
    """The product's photo, made by Muse Image the first time."""
    out = PHOTOS / f"{name}.png"
    if not out.exists():
        image.generate(f"{what} {STYLE}", size="1024x1536", out=out)
    return out


def log(line: str) -> None:
    print(line, flush=True)
    SUMMARY.parent.mkdir(exist_ok=True)
    with SUMMARY.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Photos and ads for 30 new products.")
    parser.add_argument("only", nargs="*", help="just these, by the name's first word (kova, halo, ...)")
    parser.add_argument("--photos", action="store_true", help="only make the photos")
    args = parser.parse_args()
    chosen = [a for a in ADS if not args.only or a[0].split("_")[0] in args.only]
    for name, what, _, _ in chosen:
        try:
            photo(name, what)
        except Exception as e:   # noqa: BLE001 -- that ad is skipped, the rest go on
            log(f"{name}: no photo ({e})")
    if args.photos:
        return
    log(f"\n=== batch of {len(chosen)} started {time.strftime('%Y-%m-%d %H:%M')} ===")
    made = 0
    for i, (name, _, category, brief) in enumerate(chosen, 1):
        picture = PHOTOS / f"{name}.png"
        if not picture.exists():
            continue
        began = time.time()
        done = subprocess.run([sys.executable, "-m", "pipeline.agents.producer", str(picture), brief,
                               "--category", category, "--format", "horizontal"], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        minutes = (time.time() - began) / 60
        if done.returncode == 0:
            made += 1
            log(f"[{i}/{len(chosen)}] {name}: done in {minutes:.0f} min: {done.stdout.strip().splitlines()[0]}")
        else:
            why = (done.stderr.strip().splitlines() or ["?"])[-1][:300]
            log(f"[{i}/{len(chosen)}] {name}: FAILED after {minutes:.0f} min: {why}")
    log(f"=== {made} of {len(chosen)} made, finished {time.strftime('%Y-%m-%d %H:%M')} ===")


if __name__ == "__main__":
    main()
