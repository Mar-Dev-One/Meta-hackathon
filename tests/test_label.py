"""The label goes on the part its band lies on, kept to that part's side
(two ads failed with a band the Studio wouldn't wrap)."""

import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from pipeline.agents.analyst.label import CutLabel, onto, printed
from pipeline.agents.analyst.segment import Region, Segmentation
from pipeline.schemas import ProfilePart


def part(name: str, profile: list[list[float]]) -> ProfilePart:
    return ProfilePart(name=name, profile=profile)


def label(from_: float, to: float) -> CutLabel:
    return CutLabel(Image.new("RGBA", (8, 8)), from_=from_, to=to, arc=360.0)


# An ice cream tub: the label read 1.5 mm past the tub, into the lid.
TUB = [part("body", [[0, 0], [0.0044, 0], [0.0355, 0.0218], [0.04, 0.0812], [0, 0.0812]]),
       part("cap", [[0, 0.0812], [0.04, 0.0812], [0.04, 0.0993], [0, 0.1]])]
# A tube on its cap that segmentation called nearly all cap.
TUBE = [part("body", [[0, 0], [0.0036, 0], [0.0036, 0.0001], [0, 0.0001]]),
        part("cap", [[0, 0.0001], [0.0052, 0.0001], [0.0217, 0.1297], [0, 0.13]])]


class Onto(unittest.TestCase):
    def test_a_band_past_its_part_is_kept_to_it(self):
        cut = onto(label(0.0, 0.08268), TUB)
        self.assertEqual(cut.part, "body")
        self.assertAlmostEqual(cut.to, 0.0807)
        self.assertGreater(cut.from_, 0)

    def test_it_goes_on_the_part_it_lies_on(self):
        cut = onto(label(0.02249, 0.0906), TUBE)
        self.assertEqual((cut.part, cut.from_, cut.to), ("cap", 0.02249, 0.0906))

    def test_a_label_on_no_part_is_dropped(self):
        self.assertIsNone(onto(label(0.2, 0.3), TUB))


def can(letters: bool) -> Segmentation:
    """A blue can, darker towards its sides, with a highlight stripe and
    specks of noise; white letters on its front if `letters`."""
    w, h = 300, 600
    x = np.linspace(-1, 1, 200)
    shade = 0.55 + 0.45 * np.sqrt(1 - x ** 2) + 0.25 * np.exp(-((x + 0.4) / 0.08) ** 2)   # round, and a highlight
    rgb = np.full((h, w, 3), 90.0)
    rgb[100:500, 50:250] = np.clip(np.array([20, 110, 210])[None, None, :] * shade[None, :, None], 0, 255)
    rng = np.random.default_rng(1)
    for y, xx in rng.integers([110, 60], [490, 240], (40, 2)):
        rgb[y, xx] = 255   # single-pixel specks
    if letters:
        rgb[250:330, 90:210] = 245
    mask = np.zeros((h, w), np.uint8)
    mask[100:500, 50:250] = 255
    image = Image.fromarray(rgb.astype(np.uint8))
    product = Region("product", "can", Image.fromarray(mask), (50, 100, 250, 500))
    return Segmentation(Path("can.png"), image, product)


class Printed(unittest.TestCase):
    def test_letters_on_the_body_are_its_label(self):
        found = printed(can(letters=True))
        self.assertIsNotNone(found)
        left, top, right, bottom = found.box
        self.assertTrue(85 <= left <= 92 and 205 <= right <= 215 and 245 <= top <= 252 and 328 <= bottom <= 335)

    def test_shade_highlights_and_specks_are_not(self):
        self.assertIsNone(printed(can(letters=False)))


if __name__ == "__main__":
    unittest.main()
