"""The critic: a built shot in, scores and fixes out.

    measure.py   the measured checks: framing, cuts, separation, clipping, palette, titles over the product
    judge.py     Muse Spark vision: the rubric's scores and fixes in storyboard terms, bound by the measurements
"""

from .judge import CriticError, judge
from .measure import Flag, Frame, ShotMeasure, measure, sheet

__all__ = ["CriticError", "Flag", "Frame", "ShotMeasure", "judge", "measure", "sheet"]
