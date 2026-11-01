"""A brand the photo doesn't show comes from the brief or the photo's file
name, never invented (MONO's keyboard became "KEYCRAFT")."""

import unittest

from pipeline.agents.producer import brand_hint
from pipeline.schemas.brand import HELD, PartMaterial


class BrandHint(unittest.TestCase):
    def test_from_the_brief(self):
        self.assertEqual(brand_hint("A launch ad for VOLT, loud and fast, 15 s.", "x/IMG_2031.jpg", "controller"),
                         "VOLT")

    def test_not_the_trades_capitals(self):
        self.assertEqual(brand_hint("Sunscreen ad, SPF 50, a CGI beach, 30 s.", "x/cove_sunscreen.png",
                                    "sunscreen tube"), "COVE")

    def test_from_the_file_name(self):
        self.assertEqual(brand_hint("Mechanical keyboard ad, 45 seconds.", "x/mono_keyboard.png",
                                    "mechanical keyboard"), "MONO")

    def test_not_a_camera_name_or_the_product(self):
        for name in ("IMG_2031.jpg", "images.png", "keyboard_photo.png", "DSC0042.jpg", "20261101.png"):
            self.assertIsNone(brand_hint("Keyboard ad, 15 s.", f"x/{name}", "mechanical keyboard"), name)


class HeldLiquid(unittest.TestCase):
    def glass(self, **liquid) -> PartMaterial:
        return PartMaterial(name="body", looks_like="clear glass", color="#FFFFFF", metallic=0, roughness=0.05,
                            transmission=1.0, **liquid)

    def test_a_coloured_liquid_shows_its_own_colour(self):   # honey in front of a dark set went black
        surface = self.glass(attenuation_color="#D3983E", attenuation_distance=0.08).surface()
        self.assertEqual((surface["color"], surface["transmission"]), ("#D3983E", HELD))
        self.assertEqual(surface["attenuation_color"], "#D3983E")

    def test_empty_glass_stays_clear(self):
        surface = self.glass().surface()
        self.assertEqual((surface["color"], surface["transmission"]), ("#FFFFFF", 1.0))


if __name__ == "__main__":
    unittest.main()
