"""The set: props placed clear of the product and of the pedestal's edge,
the rules that keep a draft buildable, the look's own consistency."""

import asyncio
import importlib
import math
import unittest
from unittest import mock

from pipeline.agents.director import write
from pipeline.schemas import Backdrop, CameraMove, Environment, Pedestal, Product, PropPlace

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

    def test_a_prop_with_no_floor_is_taken_out(self):   # a kettle's wooden bowl failed its ad, three drafts running
        floating = storyboard(environment=Environment(show_skybox=True), pedestal=Pedestal(width=0.2, height=0.1),
                              props=[PropPlace(prop="lemon", angle=120, gap=2.0)])
        repaired, notes = write.repair(floating)
        self.assertEqual(repaired.look.props, [])
        self.assertFalse(any("would float" in p for p in write.problems(repaired, None, repaired.length)))
        self.assertTrue(notes)


class Hero(unittest.TestCase):
    def test_a_three_quarter_hero_is_turned_to_the_front(self):   # five side-on products failed on it
        sb = storyboard()
        shots = sb.shots[:-1] + [sb.shots[-1].model_copy(update={"camera": CameraMove(move="static", azimuth=-40)})]
        repaired, notes = write.repair(sb.model_copy(update={"shots": shots}))
        self.assertEqual(repaired.shots[-1].camera.azimuth, -write.HERO_AZIMUTH)   # on the side Spark chose
        self.assertFalse(any("must be the hero" in p for p in write.problems(repaired, None, repaired.length)))

    def test_a_hero_from_the_front_is_left(self):
        sb = storyboard()
        shots = sb.shots[:-1] + [sb.shots[-1].model_copy(update={"camera": CameraMove(move="static", azimuth=10)})]
        sb = sb.model_copy(update={"shots": shots})
        self.assertEqual(write.repair(sb), (sb, []))


class Flask(unittest.TestCase):
    def test_a_flat_flask_is_edge_on_from_its_sides(self):   # SMERALDA's and SOLARE's were spun into balls
        self.assertEqual(write.edge_on(Product(template="perfume", depth=0.4)), [90.0, 270.0])
        self.assertIsNone(write.edge_on(Product(template="perfume")))

    def test_the_depth_reaches_the_studio(self):
        calls = []

        class Recorder:
            async def call(self, method, **params):
                calls.append(params)

        asyncio.run(build.create_product(Recorder(), Product(template="perfume", depth=0.4), 0.1))
        self.assertEqual(calls[0]["depth"], 0.4)


class Lights(unittest.TestCase):
    def test_a_key_is_kept_to_the_studios_limit(self):   # LUMIERE's chandelier's rim asked for 1014
        calls = []

        class Recorder:
            async def call(self, method, **params):
                calls.append((method, params))

        sb = storyboard()
        sb = sb.model_copy(update={"look": sb.look.model_copy(update={
            "lighting": sb.look.lighting.model_copy(update={"fade_in": 2.5})})})
        with mock.patch.object(build, "build_scene", mock.AsyncMock(return_value={"light_rim": 1013.99})), \
                mock.patch.object(build, "add_motion", mock.AsyncMock()), \
                mock.patch.object(build, "add_titles", mock.AsyncMock()):
            asyncio.run(build.build(Recorder(), sb))
        keys = next(p["keys"] for m, p in calls if m == "timeline.set_track")
        self.assertEqual(keys[-1]["value"], build.KEY_INTENSITY)


class Matte(unittest.TestCase):
    def test_a_rough_pedestal_hardly_reflects_the_lights(self):   # NOCTIS's black plinth glared white
        self.assertEqual(build.pedestal_args(Pedestal(roughness=0.85))["specular"], build.MATTE_SPECULAR)

    def test_a_sheen_keeps_its_reflections(self):
        self.assertNotIn("specular", build.pedestal_args(Pedestal(roughness=0.3)))


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
