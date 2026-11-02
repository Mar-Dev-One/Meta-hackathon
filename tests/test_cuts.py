"""Dips to black: only into the hero, and short."""

import importlib
import unittest

from pipeline.agents.director import write
from pipeline.schemas import CameraMove

finish = importlib.import_module("pipeline.encode.finish")   # the module (pipeline.encode.finish is also its function)

from .helpers import storyboard


def with_dips(sb, *indices):
    for i in indices:
        sb.shots[i].transition = "dip"
    return sb


class Dips(unittest.TestCase):
    def test_only_into_the_hero(self):
        self.assertEqual(with_dips(storyboard(), 1, 2).dips(), [6.0])
        self.assertEqual(with_dips(storyboard(), 1).dips(), [])
        self.assertEqual(storyboard().dips(), [])

    def test_a_mid_ad_dip_doesnt_excuse_a_jump_cut(self):
        sb = storyboard()
        for shot in sb.shots:
            shot.camera = CameraMove(move="static", azimuth=0.0)
        self.assertEqual(len(write.jump_cuts(sb)), 2)
        self.assertEqual(len(write.jump_cuts(with_dips(sb, 1))), 2)
        self.assertEqual(len(write.jump_cuts(with_dips(sb, 2))), 1)

    def test_a_dip_is_a_blink(self):
        self.assertLessEqual(finish.DIP, 0.4)
        self.assertIn("/0.200", finish.dips([6.0]))


if __name__ == "__main__":
    unittest.main()
