"""A batch of 50 ads with voice-over for 50 new products, 15 to 45 seconds:
small and big, everyday to luxurious, glass, metal and rough materials.
Each product's photo is made by Muse Image (fictional brands,
Assets/photos/voice/, made once), then its ad, one after the other,
horizontal, with --voice. A failure is logged and the batch carries on; a
summary is written to runs/voice_summary.txt as it goes.

    python scripts/voice_ads.py              # all 50
    python scripts/voice_ads.py --photos     # only the photos
    python scripts/voice_ads.py crysta vela  # just these
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.meta import image  # noqa: E402

PHOTOS = ROOT / "Assets" / "photos" / "voice"
SUMMARY = ROOT / "runs" / "voice_summary.txt"

STYLE = ("Studio product photograph, straight-on front view at eye level, the whole product centered with space "
         "around it, plain light grey seamless background, soft even light, sharp focus, no hands, no people, no "
         "props, no other objects.")

# name, what it is (for the photo), category, brief
ADS = [
    # glass
    ("crysta_decanter", "A heavy cut-crystal whisky decanter with a faceted stopper, filled with amber whisky, 'CRYSTA' etched on it.",
     "crystal decanter", "Whisky decanter ad: rich, masculine, a private evening by the fire, 30 seconds."),
    ("vela_wineglass", "A tall thin-stemmed crystal wine glass holding red wine, 'VELA' etched on its foot.",
     "wine glass", "Wine glass ad: refined, candlelit dinner, elegant, 20 seconds."),
    ("maren_vase", "A tall hand-blown glass vase in deep sea blue with soft swirls, 'MAREN' on a small gold sticker.",
     "glass vase", "Glass vase ad: artisanal, coastal, calm light on the water, 25 seconds."),
    ("lune_perfume", "A round frosted-glass perfume bottle with a polished silver cap, 'LUNE' in thin silver letters.",
     "perfume bottle", "Perfume ad: dreamy, moonlit, delicate luxury, 15 seconds."),
    ("elix_serum", "A small amber glass dropper bottle of face serum with a black dropper, 'ELIX' on a cream label.",
     "serum bottle", "Face serum ad: radiant skin, clean science, golden morning light, 20 seconds."),
    ("opaline_lantern", "A glass hurricane lantern with a brass base and a white pillar candle inside, 'OPALINE' on the base.",
     "glass lantern", "Lantern ad: cosy terrace, summer dusk, soft glow, 35 seconds."),
    ("fizzo_soda", "A clear glass soda bottle of bright red cherry soda with a metal crown cap, 'FIZZO' on a retro label.",
     "soda bottle", "Cherry soda ad: playful, retro diner, fizzy and fun, 15 seconds."),
    ("terra_terrarium", "A geometric glass terrarium with brass edges holding moss and small succulents, 'TERRA' on a brass tag.",
     "glass terrarium", "Terrarium ad: a tiny garden, calm, nature at home, 30 seconds."),
    ("clara_teapot", "A clear glass teapot with an infuser full of golden tea, 'CLARA' printed small on the lid.",
     "glass teapot", "Glass teapot ad: slow afternoon, tea unfurling, peaceful, 25 seconds."),
    ("glimmer_snowglobe", "A snow globe on a dark wooden base with a tiny pine forest inside and falling snow, 'GLIMMER' on the base.",
     "snow globe", "Snow globe ad: winter magic, nostalgic, a gift to remember, 20 seconds."),
    ("lumiere_chandelier", "A large crystal chandelier with tiers of glass drops and gold arms, 'LUMIERE' on a small gold plate.",
     "crystal chandelier", "Chandelier ad: grand, opulent, a palace ballroom glow, 40 seconds."),
    # metal
    ("orlo_shaker", "A polished chrome cocktail shaker with a copper cap, 'ORLO' engraved on it.",
     "cocktail shaker", "Cocktail shaker ad: stylish bar, night life, the perfect pour, 20 seconds."),
    ("tempra_watch", "A stainless steel dive watch with a black dial and a ceramic bezel on a steel bracelet, 'TEMPRA' on the dial.",
     "wristwatch", "Dive watch ad: precise, adventurous, deep blue, built to last, 30 seconds."),
    ("coppa_kettle", "A gleaming copper stovetop kettle with a brass handle, 'COPPA' stamped on its side.",
     "copper kettle", "Copper kettle ad: rustic kitchen, warmth, an old-world ritual, 25 seconds."),
    ("ember_skillet", "A rough black cast-iron skillet with a long handle, 'EMBER' cast into the handle.",
     "cast iron skillet", "Cast iron skillet ad: fire, crafted, generations of cooking, 30 seconds."),
    ("blaze_trumpet", "A polished brass trumpet with three silver valves, 'BLAZE' engraved on the bell.",
     "trumpet", "Trumpet ad: jazz club, soulful, a spotlight on stage, 35 seconds."),
    ("trek_tumbler", "A matte stainless steel insulated tumbler with a slide lid, 'TREK' laser-etched on it.",
     "steel tumbler", "Travel tumbler ad: on the go, fresh, everyday adventure, 15 seconds."),
    ("solene_ring", "A white gold ring with a large oval sapphire surrounded by small diamonds, 'SOLENE' on a tiny tag.",
     "sapphire ring", "Sapphire ring ad: timeless love, rare, the moment of a proposal, 20 seconds."),
    ("kairo_pocketwatch", "An antique gold pocket watch, open, with a white enamel dial and a chain, 'KAIRO' on the dial.",
     "pocket watch", "Pocket watch ad: heritage, time passed down, cinematic, 40 seconds."),
    ("voya_suitcase", "A large ribbed aluminium suitcase with black corners and wheels, 'VOYA' on a metal badge.",
     "aluminium suitcase", "Suitcase ad: first-class travel, the world awaits, 45 seconds."),
    ("crema_mixer", "A chrome stand mixer with a steel bowl and a whisk, 'CREMA' on its arm.",
     "stand mixer", "Stand mixer ad: baking with love, a Sunday kitchen, 30 seconds."),
    ("ironclad_kettlebell", "A rough black cast-iron kettlebell with a wide handle, '16 KG' and 'IRONCLAD' on it.",
     "kettlebell", "Kettlebell ad: raw strength, gritty gym, no excuses, 15 seconds."),
    ("ocula_camera", "A vintage rangefinder film camera with a silver metal body and black leatherette, 'OCULA' on the front.",
     "film camera", "Film camera ad: street photography, timeless moments, black and white soul, 35 seconds."),
    ("vanta_motorbike", "A matte black cafe racer motorcycle with chrome details and a brown leather seat, 'VANTA' on the tank.",
     "motorcycle", "Motorcycle ad: freedom, open road, raw power, 45 seconds."),
    ("corsa_bicycle", "A lightweight road bicycle with a glossy red carbon frame and thin black tyres, 'CORSA' on the frame.",
     "road bicycle", "Road bike ad: speed, mountain climbs, Italian passion, 40 seconds."),
    ("glido_scooter", "A sleek electric kick scooter in matte grey with a lit display on the handlebar, 'GLIDO' on the deck.",
     "electric scooter", "Electric scooter ad: city mornings, clean and quick, 25 seconds."),
    ("ticker_robot", "A vintage wind-up tin toy robot in red and silver with a key on its back, 'TICKER' on its chest.",
     "tin toy robot", "Toy robot ad: playful, nostalgic, wonder of childhood, 20 seconds."),
    # rough, natural, crafted
    ("kiln_mug", "A handmade stoneware mug with a speckled oatmeal glaze and a rough unglazed base, 'KILN' stamped on it.",
     "ceramic mug", "Stoneware mug ad: handmade, quiet mornings, earthy, 20 seconds."),
    ("olea_planter", "A large terracotta pot holding a small olive tree, 'OLEA' pressed into the clay.",
     "potted olive tree", "Olive tree planter ad: Mediterranean sun, slow living, 30 seconds."),
    ("ridge_boots", "A pair of rugged brown leather hiking boots with red laces and thick soles, 'RIDGE' on the heel.",
     "hiking boots", "Hiking boots ad: mountains, mud and miles, made for the wild, 35 seconds."),
    ("norda_beanie", "A chunky cream wool knit beanie with a pompom, 'NORDA' on a small leather patch.",
     "wool beanie", "Wool beanie ad: cosy, snowy north, warm and soft, 15 seconds."),
    ("gambit_chess", "A wooden chess set on a walnut and maple board with hand-carved pieces, 'GAMBIT' burned into the board's edge.",
     "chess set", "Chess set ad: strategy, quiet focus, a game for generations, 40 seconds."),
    ("soleil_hat", "A wide-brimmed woven straw sun hat with a black ribbon, 'SOLEIL' on the ribbon.",
     "straw hat", "Straw hat ad: Riviera summer, effortless, sun on the skin, 20 seconds."),
    ("granito_mortar", "A heavy grey granite mortar and pestle with a rough outside and smooth bowl, 'GRANITO' carved on it.",
     "mortar and pestle", "Mortar and pestle ad: herbs and spices, honest cooking, 25 seconds."),
    ("sapo_soap", "A rough handmade bar of olive oil soap with lavender flecks, 'SAPO' stamped on it.",
     "soap bar", "Handmade soap ad: natural, gentle, a calm bath, 15 seconds."),
    ("homer_glove", "A tan leather baseball glove with dark laces, 'HOMER' stitched on the strap.",
     "baseball glove", "Baseball glove ad: summer games, team spirit, golden hour, 30 seconds."),
    ("napa_armchair", "A rattan lounge armchair with a cream linen cushion, 'NAPA' on a small brass tag.",
     "rattan armchair", "Rattan armchair ad: slow summer living, a sunny veranda, 40 seconds."),
    ("lofta_sofa", "A three-seat sofa in sage green velvet with brass legs, 'LOFTA' on a small label.",
     "velvet sofa", "Velvet sofa ad: modern home, comfort and style, a lazy Sunday, 45 seconds."),
    ("arbor_chair", "A solid oak dining chair with a curved back and a woven seat, 'ARBOR' burned under the seat.",
     "oak chair", "Oak chair ad: Scandinavian design, built for a lifetime, 30 seconds."),
    ("picniq_basket", "A wicker picnic basket with leather straps and a red gingham lining, 'PICNIQ' on a leather tag.",
     "picnic basket", "Picnic basket ad: sunny meadow, friends, simple joys, 25 seconds."),
    ("greystone_lamp", "A table lamp with a raw concrete base and a linen drum shade, 'GREYSTONE' on the base.",
     "concrete lamp", "Concrete lamp ad: minimal, industrial loft, warm evening light, 35 seconds."),
    ("rover_duffel", "A large leather weekender duffel bag in cognac brown with brass buckles, 'ROVER' embossed on it.",
     "leather duffel bag", "Leather duffel ad: weekend escape, rugged elegance, 40 seconds."),
    # everyday
    ("vortex_blender", "A high-speed blender with a clear jar full of a green smoothie, a black base, 'VORTEX' on the base.",
     "blender", "Blender ad: healthy energy, bright kitchen, morning boost, 30 seconds."),
    ("swift_vacuum", "A cordless stick vacuum cleaner in white and teal, standing upright, 'SWIFT' on the handle.",
     "stick vacuum", "Cordless vacuum ad: effortless clean, bright home, 25 seconds."),
    ("asana_mat", "A rolled-up cork yoga mat tied with a cotton strap, 'ASANA' printed on it.",
     "yoga mat", "Yoga mat ad: calm, balance, morning practice, 20 seconds."),
    ("quacko_duck", "A classic yellow rubber duck with an orange beak, 'QUACKO' printed on its side.",
     "rubber duck", "Rubber duck ad: silly, joyful, bath time fun, 15 seconds."),
    ("volley_racket", "A tennis racket with a white and electric blue frame and tight strings, 'VOLLEY' on the frame.",
     "tennis racket", "Tennis racket ad: power, precision, match point, 35 seconds."),
    ("throne_chair", "A black and red gaming chair with a high back and armrests, 'THRONE' embroidered on the headrest.",
     "gaming chair", "Gaming chair ad: neon nights, focus, level up, 45 seconds."),
    ("chilla_fridge", "A retro rounded refrigerator in pastel mint with a chrome handle, 'CHILLA' on the door.",
     "retro refrigerator", "Retro fridge ad: fifties charm, a cheerful kitchen, 40 seconds."),
    ("allegro_piano", "A black lacquered grand piano with its lid open, 'ALLEGRO' in gold above the keys.",
     "grand piano", "Grand piano ad: concert hall, emotion, timeless elegance, 45 seconds."),
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
    parser = argparse.ArgumentParser(description="Photos and ads with voice-over for 50 new products.")
    parser.add_argument("only", nargs="*", help="just these, by the name's first word (crysta, vela, ...)")
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
    log(f"\n=== batch of {len(chosen)} with voice-over started {time.strftime('%Y-%m-%d %H:%M')} ===")
    made = 0
    for i, (name, _, category, brief) in enumerate(chosen, 1):
        picture = PHOTOS / f"{name}.png"
        if not picture.exists():
            continue
        began = time.time()
        done = subprocess.run([sys.executable, "-m", "pipeline.agents.producer", str(picture), brief,
                               "--category", category, "--format", "horizontal", "--voice"], cwd=ROOT,
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
