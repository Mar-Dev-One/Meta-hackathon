"""The label goes on the part its band lies on, kept to that part's side
(two ads failed with a band the Studio wouldn't wrap)."""

import unittest

from PIL import Image

from pipeline.agents.analyst.label import CutLabel, onto
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


if __name__ == "__main__":
    unittest.main()
