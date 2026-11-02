"""The critic loop keeps its best round when a revision fails, whatever the
failure: the ad is still made."""

import asyncio
import importlib
import unittest
from unittest import mock

from pipeline.meta.client import MetaError

from .helpers import storyboard

loop = importlib.import_module("pipeline.agents.critic.loop")


class FakeRun:
    def __init__(self):
        self.events = []

    def event(self, kind, **fields):
        self.events.append((kind, fields))

    def save_json(self, name, data):
        return name

    def path(self, *parts):
        return "/".join(parts)

    def output(self, *args):
        pass


def round_(index, sb, score, passed=False):
    r = mock.Mock(spec=loop.Round, index=index, storyboard=sb, passed=passed, score=score)
    return r


class RevisionFails(unittest.TestCase):
    def test_spark_out_of_turns_keeps_the_best_round(self):
        first, second = storyboard(), storyboard((2.0, 3.0, 3.5))
        looks = iter([round_(0, first, (4, 5, 7.4)), round_(1, second, (2, 5, 6.2))])
        revisions = iter([(second, ["shots[0].duration: 3.0 -> 2.0"]),
                          MetaError("muse-spark-1.3", "still calling tools after 10 turns (10 calls)")])

        async def look(*args, **kwargs):
            return next(looks)

        async def revise(*args, **kwargs):
            out = next(revisions)
            if isinstance(out, Exception):
                raise out
            return out

        built = []

        async def build(studio, sb):
            built.append(sb)

        run = FakeRun()
        with mock.patch.object(loop, "look", look), mock.patch.object(loop, "revise", revise), \
                mock.patch.object(loop, "build", build), mock.patch.object(loop, "fix_text", lambda *a: ""):
            sb, history = asyncio.run(loop.refine(None, first, None, run))
        self.assertIs(sb, first)                       # round 0 scored best
        self.assertEqual(built, [first])               # and the Studio is built with it again
        self.assertEqual(len(history), 2)
        self.assertIn("revision_failed", [k for k, _ in run.events])


if __name__ == "__main__":
    unittest.main()
