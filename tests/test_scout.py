"""The scout: a product that isn't round and has no model to stand in for
it stops the ad (traced, the drone was a mushroom); a round one is traced."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline.agents import scout
from pipeline.catalog.common import CatalogError
from pipeline.runs import Run

DRONE = scout.Shape(reason="an X of four arms from above", round=False, queries=["camera drone"])
JAR = scout.Shape(reason="a circle from above", round=True, queries=[])


class NoModel(unittest.TestCase):
    def find(self, shape, pick=None, error=None):
        with tempfile.TemporaryDirectory() as folder, Run.create("scout", base=Path(folder)) as run, \
                mock.patch.object(scout, "shape", side_effect=error or (lambda *_: shape)), \
                mock.patch.object(scout, "pick", return_value=pick):
            return asyncio.run(scout.scout(run, "photo.png", "camera drone"))

    def test_none_fits(self):
        answer = scout.Pick(reason="none is a quadcopter", choices=[])
        with self.assertRaisesRegex(scout.NoModel, "none is a quadcopter"):
            self.find(DRONE, ([], answer, None))

    def test_the_search_fails(self):
        with mock.patch.object(scout, "pick", side_effect=CatalogError("down")), \
                self.assertRaisesRegex(scout.NoModel, "search failed"):
            with tempfile.TemporaryDirectory() as folder, Run.create("scout", base=Path(folder)) as run, \
                    mock.patch.object(scout, "shape", return_value=DRONE):
                asyncio.run(scout.scout(run, "photo.png", "camera drone"))

    def test_a_round_one_is_traced(self):
        self.assertEqual(self.find(JAR), (None, None))

    def test_its_shape_unknown_it_is_traced(self):   # Spark down: as before
        self.assertEqual(self.find(None, error=CatalogError("down")), (None, None))


if __name__ == "__main__":
    unittest.main()
