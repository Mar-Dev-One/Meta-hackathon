"""The prop library: objects to set around the product, from Poly Haven
(all CC0, scanned or modelled at their real sizes), each picked to sit
beside a product a few to a few tens of centimetres tall, and kept at its
real size (a lemon is a lemon's size beside the bottle).

    path = prop_file("lemon")      # downloaded once into cache/polyhaven/, as one GLB
    PROPS["lemon"].text            # what the director reads
"""

from dataclasses import dataclass
from pathlib import Path

from . import polyhaven
from .common import Candidate


@dataclass(frozen=True)
class Prop:
    key: str        # Poly Haven's id
    text: str       # what it is, for the director

    @property
    def candidate(self) -> Candidate:
        m = polyhaven.catalogue()[self.key]
        return Candidate(source="polyhaven", id=self.key, name=m["name"],
                         author=", ".join(m.get("authors", {})) or "Poly Haven", licence="cc0",
                         page=f"https://polyhaven.com/a/{self.key}", thumbnail="", faces=m.get("polycount", 0))


PROPS = {
    # stone and shell: spa, skincare, fragrance, outdoor
    "rust_rock": Prop("stone_01", "a rough rust-brown rock with pale patches, palm-sized"),
    "slate": Prop("rock_09", "a flat layered brown-grey slate, palm-sized"),
    "pale_stone": Prop("moon_rock_01", "a smooth pale sandstone, flat-topped, two hands wide"),
    "shell": Prop("lambis_shell", "a spiky conch shell, cream with orange-brown stripes, palm-sized"),
    # plants
    "succulent": Prop("potted_plant_04", "a small spiky succulent in a white pot, 27 cm tall"),
    # fruit: fresh, citrus, summer, food and drink
    "lemon": Prop("lemon", "a lemon, 9.5 cm"),
    "lime": Prop("food_lime_01", "a lime, 7.5 cm"),
    "apple": Prop("food_apple_01", "a glossy red apple, 10 cm"),
    "pomegranate": Prop("food_pomegranate_01", "a red pomegranate, 11.5 cm"),
    "kiwi": Prop("food_kiwi_01", "a brown furry kiwi fruit, 9 cm"),
    "avocado": Prop("food_avocado_01", "a dark pebbled avocado, 14 cm"),
    "lychee": Prop("food_lychee_01", "a pink lychee, 5 cm"),
    "croissant": Prop("croissant", "a golden croissant, 20 cm long: breakfast, coffee"),
    # vessels and wood: home, kitchen, craft
    "bottle_vase": Prop("ceramic_vase_01", "a white glazed bottle vase with a narrow neck, 40 cm tall"),
    "block_vase": Prop("ceramic_vase_03", "a slim square-sided cream stone vase, 41 cm tall"),
    "brass_vase": Prop("brass_vase_01", "a slender polished brass vase, 69 cm tall: luxury, behind the product"),
    "clay_pot": Prop("planter_pot_clay", "an empty weathered terracotta pot, 22 cm tall"),
    "jug": Prop("jug_01", "a white ceramic jug painted with pink tulips, 21 cm tall"),
    "wooden_bowl": Prop("wooden_bowl_01", "a rustic hand-carved wooden bowl, 31 cm wide"),
    "wooden_plate": Prop("carved_wooden_plate", "a flat pale carved wooden plate, 27 cm wide"),
    "cutting_board": Prop("wooden_cutting_board", "a worn wooden cutting board, 45 cm long, lying flat"),
}


def prop_file(name: str) -> Path:
    """The prop's model as one GLB, downloaded the first time."""
    return polyhaven.download(PROPS[name].candidate)
