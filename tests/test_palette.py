"""The photo's palette: a part's colour is how it looks lit, without its
shade and its specular highlights."""

import unittest

import numpy as np

from pipeline.agents.analyst.palette import _lit


def cluster(lightness: float, share: float, chroma: float = 0.0):
    lab = np.array([lightness, chroma, 0.0])
    return lab, np.array([lightness * 2.55] * 3), share


class Lit(unittest.TestCase):
    def test_a_highlight_is_left_out(self):   # a silver cap: two of its clusters near-white (it once raised)
        metal, sheen, glint = cluster(70, 0.5), cluster(95, 0.3), cluster(97, 0.2)
        self.assertEqual([c[2] for c in _lit([metal, sheen, glint])], [0.5])

    def test_all_highlight_is_kept(self):   # a white product: nothing else to show
        white = [cluster(94, 0.6), cluster(96, 0.4)]
        self.assertEqual(len(_lit(white)), 2)

    def test_shade_is_left_out(self):
        shade, lit = cluster(20, 0.2, chroma=30), cluster(60, 0.8, chroma=30)
        self.assertEqual([c[2] for c in _lit([shade, lit])], [0.8])


if __name__ == "__main__":
    unittest.main()
