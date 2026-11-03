"""Downloaded models: what they came standing on taken off (and nothing of
the product), repainted in the photo's colours, reframed for 9:16."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from pipeline.agents.analyst.palette import to_lab
from pipeline.schemas import CameraMove
from pipeline.studio import models, recolour
from pipeline.studio.reframe import CLOSE, _scaled

from .helpers import box, storyboard

MUG = ((0.10, 0.12, 0.10), (0, 0.064, 0))   # standing 4 mm up (3% of it): on whatever is under it


class StripBase(unittest.TestCase):
    def strip(self, *under):
        return models.strip_base([box(*MUG), *under])

    def test_a_coaster_goes(self):   # BREW's mug came on one, 2.7% of its height
        self.assertGreater(self.strip(box((0.12, 0.004, 0.12), (0, 0.002, 0))), 0)

    def test_a_ground_plane_goes(self):
        self.assertGreater(self.strip(box((0.6, 0.0001, 0.6), (0, 0.00395, 0))), 0)

    def test_a_stand_in_two_pieces_goes(self):   # one mesh, two base parts (BREVA's machine broke on it)
        stand = trimesh.util.concatenate([box((0.12, 0.004, 0.06), (0, 0.002, z)) for z in (-0.031, 0.031)])
        self.assertEqual(self.strip(stand), 24)

    def test_small_feet_stay(self):
        feet = [box((0.01, 0.004, 0.01), (x, 0.002, 0)) for x in (-0.04, 0.04)]
        self.assertEqual(self.strip(*feet), 0)

    def test_its_own_flat_bottom_stays(self):
        mug = box((0.10, 0.12, 0.10), (0, 0.06, 0))
        cap = box((0.09, 0.0001, 0.09), (0, 0.00005, 0))
        self.assertEqual(models.strip_base([mug, cap]), 0)

    def test_nothing_under_it(self):
        self.assertEqual(models.strip_base([box((0.1, 0.12, 0.1), (0, 0.06, 0))]), 0)

    def test_fit_takes_it_off_and_keeps_the_height(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder, "mug.glb")
            trimesh.Scene([box(*MUG), box((0.12, 0.004, 0.12), (0, 0.002, 0))]).export(str(source))
            fitted = models.fit(source, Path(folder, "fitted.glb"), height=0.1, up="+y")
            self.assertAlmostEqual(models.size(fitted)[0], 0.1, places=4)
            self.assertAlmostEqual(models.size(fitted)[1], 0.1 * 0.10 / 0.12, places=3)   # the mug's width, not the coaster's
            self.assertEqual(models.faces(fitted), 12)


class Finish(unittest.TestCase):
    def test_only_materials_without_a_finish_take_the_photos(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "model.glb")
            trimesh.Scene([box((0.1, 0.1, 0.1), (0, 0.05, 0), [200, 50, 50, 255]),
                           box((0.05, 0.05, 0.05), (0, 0.2, 0), [50, 50, 200, 255])]).export(str(path))
            gltf, rest = models._read_glb(path)
            gltf["materials"][1]["pbrMetallicRoughness"]["roughnessFactor"] = 0.3   # a modeller's finish
            gltf["materials"][1]["pbrMetallicRoughness"]["metallicFactor"] = 0.0
            models._write_glb(path, gltf, rest)
            self.assertEqual(len(models.finish_unset(path, 0.0, 0.6)), 1)
            unset, made = (m["pbrMetallicRoughness"] for m in models._read_glb(path)[0]["materials"])
            self.assertEqual((unset["metallicFactor"], unset["roughnessFactor"]), (0.0, 0.6))
            self.assertEqual((made["metallicFactor"], made["roughnessFactor"]), (0.0, 0.3))


class Recolour(unittest.TestCase):
    def test_lab_round_trip(self):
        rgb = np.random.default_rng(0).uniform(0, 255, (500, 3))
        self.assertLess(np.abs(recolour.to_rgb(to_lab(rgb)) - rgb).max(), 1.0)

    def test_a_group_centre_lands_on_its_target(self):
        centres = to_lab(np.array([[20.0, 20, 20], [230, 230, 230]]))
        targets = to_lab(np.array([[200.0, 40, 40], [40, 200, 40]]))
        moved = recolour._move(centres, centres, targets)
        self.assertLess(np.abs(moved - targets).max(), 0.5)

    def test_paired_by_size_or_by_lightness(self):
        """A big dark body with a small light part, to a photo whose biggest colour is light."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "model.glb")
            trimesh.Scene([box((0.2, 0.2, 0.2), (0, 0.1, 0), [30, 30, 30, 255]),
                           box((0.05, 0.05, 0.05), (0, 0.3, 0), [220, 220, 220, 255])]).export(str(path))
            colours = [("#F0F0F0", 0.8), ("#101010", 0.2)]
            made = recolour.versions(path, colours, Path(folder, "out"))
            self.assertEqual(set(made), {"size", "lightness"})

            def body(glb):   # the big box's colour, as seen (sRGB)
                scene = trimesh.load(str(glb), force="scene")
                big = max(scene.geometry.values(), key=lambda m: m.area)
                return recolour._to_srgb(np.array(big.visual.material.baseColorFactor[:3]) / 255)

            self.assertGreater(body(made["size"]).mean(), 200)        # the biggest region took the biggest colour
            self.assertLess(body(made["lightness"]).mean(), 40)       # the darkest took the darkest


class Caps(unittest.TestCase):
    GLASS = {"color": "#383737", "roughness": 0.05, "transmission": 0.9}
    GOLD = {"color": "#D6BD94", "metallic": 1.0, "roughness": 0.15}

    def dressed(self, *meshes):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "model.glb")
            trimesh.Scene(list(meshes)).export(str(path))
            models.dress(path, path, {"body": self.GLASS, "cap": self.GOLD})
            scene = trimesh.load(str(path), force="scene")
            return sorted((round(float(m.bounds[0][1]), 3), m.visual.material.metallicFactor)
                          for m in scene.geometry.values())

    def test_a_stopper_in_the_bottles_mesh_is_the_cap(self):   # NOCTIS's: its gold cap came out smoked glass
        bottle = trimesh.util.concatenate([box((0.09, 0.107, 0.03), (0, 0.0535, 0)),
                                           box((0.05, 0.017, 0.05), (0, 0.1315, 0))])
        self.assertEqual(self.dressed(bottle), [(0.0, 0.0), (0.123, 1.0)])

    def test_a_mesh_all_of_the_body_stays_whole(self):
        self.assertEqual(self.dressed(box((0.09, 0.14, 0.03), (0, 0.07, 0))), [(0.0, 0.0)])


class Decal(unittest.TestCase):   # Maison Héritage's label: a 3D model's product went without one
    def test_it_lies_on_the_front_and_glass_stays_glass(self):
        with tempfile.TemporaryDirectory() as folder:
            path, image = Path(folder, "model.glb"), Path(folder, "decal.png")
            trimesh.Scene([box((0.06, 0.14, 0.04), (0, 0.07, 0), [200, 200, 200, 120])]).export(str(path))
            models.dress(path, path, {"body": Caps.GLASS})
            Image.new("RGBA", (40, 30), (255, 255, 255, 255)).save(image)
            self.assertTrue(models.add_decal(path, image, (0.1, 0.3, 0.9, 0.6)))
            scene = trimesh.load(str(path), force="scene")
            decal = scene.geometry["decal"]
            (x0, y0, z0), (x1, y1, z1) = decal.bounds
            self.assertAlmostEqual(z0, 0.02 + models.DECAL_LIFT, places=5)   # on the front face, just off it
            self.assertAlmostEqual(z1, 0.02 + models.DECAL_LIFT, places=5)
            self.assertAlmostEqual(x0, -0.024, places=4)
            self.assertAlmostEqual(y1, 0.14 * 0.7, places=4)               # the photo's top is the model's top
            self.assertGreater(decal.face_normals[:, 2].mean(), 0.99)       # facing the camera
            gltf, _ = models._read_glb(path)
            glass = [m for m in gltf["materials"] if m.get("name", "").startswith("glass")]
            self.assertIn("KHR_materials_transmission", glass[0].get("extensions", {}))
            self.assertEqual(next(m for m in gltf["materials"] if m.get("name") == "decal")["alphaMode"], "BLEND")


class Reframe(unittest.TestCase):
    def test_fills_scaled_close_ups_kept(self):
        sb = storyboard([3.0, 3.0, 3.5]).model_copy()
        shots = [sb.shots[0].model_copy(update={"camera": CameraMove(move="dolly", fill=0.6, from_fill=0.4, to_fill=0.6)}),
                 sb.shots[1].model_copy(update={"camera": CameraMove(move="static", fill=0.9)}),
                 sb.shots[2].model_copy(update={"camera": CameraMove(move="static", fill=0.06)})]
        scaled = _scaled(sb.model_copy(update={"shots": shots}), 0.5)
        dolly, close, small = (s.camera for s in scaled.shots)
        self.assertEqual((dolly.fill, dolly.from_fill, dolly.to_fill), (0.3, 0.2, 0.3))
        self.assertGreater(close.max_fill(), CLOSE)
        self.assertEqual(close.fill, 0.9)
        self.assertEqual(small.fill, 0.05)   # never below the schema's least


if __name__ == "__main__":
    unittest.main()
