"""Free camera paths: the schema keeps a path well formed, and the rules,
cuts and 9:16 framing read its waypoints."""

import unittest

from pydantic import ValidationError

from pipeline.agents.director.write import _azimuths, _elevations, _framing
from pipeline.schemas import CameraMove, PathPoint
from pipeline.studio.reframe import _scaled

from .helpers import storyboard

SWEEP = [PathPoint(at=0, azimuth=-60, elevation=5, fill=0.5), PathPoint(at=0.6, azimuth=10, elevation=20, fill=0.6),
         PathPoint(at=1, azimuth=40, elevation=45, fill=0.85)]


class Schema(unittest.TestCase):
    def test_a_path_needs_its_waypoints_in_order(self):
        CameraMove(move="path", points=SWEEP)
        for points in ([], SWEEP[:1], SWEEP[1:], [SWEEP[0], SWEEP[2], SWEEP[1]]):
            with self.assertRaises(ValidationError):
                CameraMove(move="path", points=points)

    def test_its_extremes_are_its_waypoints(self):
        camera = CameraMove(move="path", points=SWEEP)
        self.assertEqual(camera.max_fill(), 0.85)
        self.assertEqual(_elevations(camera), [5, 20, 45])     # the flat-product rule checks each
        self.assertEqual(_azimuths(camera), [-60, 10, 40])      # and the edge-on rule
        self.assertEqual(_framing(camera, end=False), (0.5, -60, 5))   # a cut reads its ends
        self.assertEqual(_framing(camera, end=True), (0.85, 40, 45))


class Reframe(unittest.TestCase):
    def test_a_paths_framing_scales_with_the_rest(self):
        medium = [p.model_copy(update={"fill": f}) for p, f in zip(SWEEP, (0.5, 0.6, 0.65))]
        sb = storyboard([3.0, 3.0, 3.5])
        for points, fills in ((medium, [0.25, 0.3, 0.325]), (SWEEP, [0.5, 0.6, 0.85])):   # one into a close-up: kept
            shots = [sb.shots[0].model_copy(update={"camera": CameraMove(move="path", points=points)}), *sb.shots[1:]]
            scaled = _scaled(sb.model_copy(update={"shots": shots}), 0.5)
            self.assertEqual([p.fill for p in scaled.shots[0].camera.points], fills)


if __name__ == "__main__":
    unittest.main()
