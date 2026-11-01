"""The set: props placed clear of the product and of the pedestal's edge,
the rules that keep a draft buildable, the look's own consistency."""

import importlib
import math
import unittest
from unittest import mock

from pipeline.agents.director import write
from pipeline.schemas import Backdrop, Environment, Pedestal, PropPlace

build = importlib.import_module("pipeline.studio.build")   # the module (pipeline.studio.build is also its function)

from .helpers import storyboard

PROP = 0.04   # every prop's radius in these tests (no downloads)


@mock.patch.object(build, "prop_radius", lambda name: PROP)
class Props(unittest.TestCase):
    def spots(self, props, pedestal=Pedestal(width=0.32, height=0.1)):
        sb = storyboard(pedestal=pedestal, props=[PropPlace(**p) for p in props])
        return sb, build.prop_spots(sb)

    def test_never_overlaps_the_product(self):
        for angle in range(-180, 181, 30):
            for gap in (0.0, 0.3, 1.5):
                sb, (spot,) = self.spots([{"prop": "lemon", "angle": angle, "gap": gap}])
                x, _, z = spot["position"]
                self.assertGreaterEqual(math.hypot(x, z) + 1e-9, build.product_radius(sb.product) + PROP)

    def test_angle_follows_the_cameras_azimuth(self):
        _, (front, right) = self.spots([{"prop": "lemon", "angle": 0, "gap": 3}, {"prop": "lime", "angle": 90, "gap": 3}])
        self.assertGreater(front["position"][2], 0)   # 0: towards a camera at azimuth 0 (+Z)
        self.assertGreater(right["position"][0], 0)   # 90: its right (+X)

    def test_on_the_pedestal_when_it_fits_else_clear_of_its_edge(self):
        _, (near, edge, far) = self.spots([{"prop": "lemon", "angle": 90, "gap": 0.0},
                                           {"prop": "lime", "angle": -90, "gap": 1.2},
                                           {"prop": "apple", "angle": 180, "gap": 4.0}])
        self.assertEqual(near["on"], "pedestal")
        self.assertEqual(near["position"][1], 0.1)
        for spot in (edge, far):
            self.assertEqual(spot["on"], "floor")
            self.assertEqual(spot["position"][1], 0.0)
            x, _, z = spot["position"]
            self.assertGreaterEqual(math.hypot(x, z) - PROP, 0.16 - 1e-6)   # nothing hangs over the edge
        self.assertGreater(edge["moved"], 0)

    def test_a_prop_with_no_floor_breaks_a_rule(self):
        floating = storyboard(environment=Environment(show_skybox=True), pedestal=Pedestal(width=0.2, height=0.1),
                              props=[PropPlace(prop="lemon", angle=120, gap=2.0)])
        self.assertTrue(any("would float" in p for p in write.problems(floating, None, floating.length)))
        standing = storyboard(props=[PropPlace(prop="lemon", angle=120, gap=2.0)])
        self.assertFalse(any("would float" in p for p in write.problems(standing, None, standing.length)))


class Rules(unittest.TestCase):
    def test_length_and_shot_limits(self):
        sb = storyboard([0.8, 3.0, 3.0])
        found = write.problems(sb, None, 10.0)
        self.assertTrue(any("add up to" in p for p in found))
        self.assertTrue(any("lasts 0.8 s" in p for p in found))

    def test_a_good_plan_passes(self):
        sb = storyboard([3.0, 3.0, 3.5], moves=["orbit", "dolly", "static"])
        self.assertEqual([p for p in write.problems(sb, None, sb.length) if "lasts" in p or "add up" in p], [])


class Look(unittest.TestCase):
    def test_a_painted_place_is_the_background(self):
        sb = storyboard(environment=Environment(painted="a sunlit terrace"), backdrop=Backdrop())
        self.assertTrue(sb.look.environment.show_skybox)
        self.assertIsNone(sb.look.backdrop)


if __name__ == "__main__":
    unittest.main()
