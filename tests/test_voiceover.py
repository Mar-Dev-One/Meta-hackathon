"""The voice-over: its lines checked against the film's time, read as MMS
can say them, laid on the ad's track without overlapping, and left out
(not failing the ad) when it can't be made. No model, network or torch."""

import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from pipeline.agents import voiceover as vo
from pipeline.encode import speech
from pipeline.encode.music import RATE

from .helpers import storyboard


def lines(*pairs):
    return vo.VoiceOver(lines=[vo.Line(text=t, start=s) for s, t in pairs])


class Phrases(unittest.TestCase):
    def test_split_where_the_punctuation_was(self):
        self.assertEqual(speech.phrases("Lumen. Warmth for quiet evenings!"), ["lumen", "warmth for quiet evenings"])

    def test_accents_off_and_only_letters(self):
        self.assertEqual(speech.phrases("Café crème — rich & smooth"), ["cafe creme", "rich smooth"])
        self.assertEqual(speech.phrases("..."), [])


class BrandSaid(unittest.TestCase):
    def test_the_brand_in_its_spoken_spelling_only(self):
        self.assertEqual(vo.said("Find your calm with LUMEN.", "LUMEN", "Loomen"), "Find your calm with Loomen.")
        self.assertEqual(vo.said("Luminous light.", "LUMEN", "Loomen"), "Luminous light.")
        self.assertEqual(vo.said("Lumen.", "LUMEN", ""), "Lumen.")


class Rules(unittest.TestCase):
    sb = storyboard()   # 9.5 s

    def test_a_good_voice_over_passes(self):
        self.assertEqual(vo.problems(lines((1.0, "A little light, at last."), (6.0, "Lumen.")), self.sb, "LUMEN"), [])

    def test_a_line_running_into_the_next(self):
        found = vo.problems(lines((1.0, "Some evenings ask for nothing but a little more light"), (3.0, "Lumen.")),
                            self.sb, "LUMEN")
        self.assertTrue(any("past" in p for p in found))

    def test_the_brand_last_numbers_as_words_and_a_late_start(self):
        found = vo.problems(lines((0.2, "Burns for 40 hours."), (6.0, "Warm.")), self.sb, "LUMEN")
        self.assertEqual(len(found), 3)


class Track(unittest.TestCase):
    def test_lines_never_overlap_and_the_track_is_the_ads_length(self):
        one = np.ones(round(2.0 * speech.SPEECH_RATE), np.float32) * 0.3   # 2 s of "speech"
        with tempfile.TemporaryDirectory() as d:
            out = speech.track([(1.0, one), (2.0, one)], 9.5, Path(d) / "voice.wav")
            with wave.open(str(out)) as w:
                audio = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2)[:, 0]
        self.assertEqual(len(audio), round(9.5 * RATE))
        loud = np.flatnonzero(np.abs(audio) > 100) / RATE
        self.assertAlmostEqual(loud[0], 1.0, places=2)
        self.assertGreater(loud[-1], 3.0 + 0.25 + 1.9)   # the second waited for the first, and a breath


class Optional(unittest.TestCase):
    def run_(self, ask=None, speak=None):
        sb, run = storyboard(), mock.MagicMock()
        run.path.side_effect = lambda *parts: Path(self.dir.name, *parts)
        answer = mock.Mock(data={"lines": [{"text": "A little light.", "start": 1.0},
                                           {"text": "Lumen.", "start": 6.0}]})
        with mock.patch.object(vo.spark, "ask", ask or (lambda *a, **k: answer)), \
                mock.patch.object(vo.speech, "speak", speak or (lambda text: np.full(8000, 0.2, np.float32))):
            return vo.voiceover(run, sb, "candle ad", mock.Mock(brand="LUMEN", category="candle", mood=["warm"],
                                                                do_not=[])), run

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        Path(self.dir.name, "final").mkdir()

    def tearDown(self):
        self.dir.cleanup()

    def test_written_spoken_and_laid_on_a_track(self):
        path, run = self.run_()
        self.assertTrue(path.exists())
        self.assertIn("voiceover", [c.args[0] for c in run.event.call_args_list])

    def test_a_failure_leaves_it_out_instead_of_failing_the_ad(self):
        def broken(text):
            raise speech.VoiceUnavailable("no torch")
        path, run = self.run_(speak=broken)
        self.assertIsNone(path)
        self.assertIn("voiceover_failed", [c.args[0] for c in run.event.call_args_list])


if __name__ == "__main__":
    unittest.main()
