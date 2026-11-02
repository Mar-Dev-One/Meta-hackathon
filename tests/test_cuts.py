"""The ad's joins: dips to black only into the hero, and short; the film's
titles gone before the end card dissolves in."""

import importlib
import unittest

from pipeline.agents.director import write
from pipeline.schemas import CameraMove, Title
from pipeline.schemas.storyboard import EndCard

finish = importlib.import_module("pipeline.encode.finish")   # the module (pipeline.encode.finish is also its function)
build = importlib.import_module("pipeline.studio.build")     # the module (pipeline.studio.build is also its function)

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



class TitlesBeforeTheCard(unittest.TestCase):
    def setUp(self):
        self.sb = storyboard()   # 9.5 s
        self.card = EndCard(name="AURELLE", background="#1a1a1a", font="serif")

    def opacity(self, title, card=True):
        sb = self.sb.model_copy(update={"end_card": self.card if card else None})
        return build.title_opacity(sb, title)

    def title(self, start):
        return Title(text="AURELLE", font="serif", size=0.07, y=0.8, color="#ffffff", start=start)

    def test_gone_when_the_card_dissolves_in(self):
        keys = self.opacity(self.title(6.5))
        self.assertEqual(keys[-1], {"t": 9.5 - finish.DISSOLVE, "value": 0})
        self.assertAlmostEqual(keys[-2]["t"], 9.5 - finish.DISSOLVE - build.TITLE_OUT)

    def test_kept_to_the_end_without_a_card(self):
        self.assertEqual([k["value"] for k in self.opacity(self.title(6.5), card=False)], [0, 1])

    def test_a_late_title_still_has_its_keys_in_order(self):
        times = [k["t"] for k in self.opacity(self.title(8.5))]
        self.assertEqual(times, sorted(set(times)))


if __name__ == "__main__":
    unittest.main()
