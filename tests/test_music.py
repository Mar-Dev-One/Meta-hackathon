"""The music: cuts on the beat within the shot limits, every mood as loud,
the director's tempo kept to its mood's range."""

import random
import unittest

import numpy as np
from pydantic import ValidationError

from pipeline.agents.director.write import HERO_MIN, SHOT_MAX, SHOT_MIN
from pipeline.encode.music import LOUDNESS, PEAK, SETTINGS, compose, cut_to_beat, loudness, mood_of, tempo_of
from pipeline.schemas import Music
from pipeline.schemas.storyboard import TEMPOS

from .helpers import storyboard


class CutToBeat(unittest.TestCase):
    def test_shots_stay_within_their_limits(self):
        """Snapping once made a shot 1.1 s and a hero 2.3 s: never again, over many plans and tempos."""
        rng = random.Random(1)
        for _ in range(400):
            n = rng.randint(2, 7)
            durations = [round(rng.uniform(SHOT_MIN, SHOT_MAX), 2) for _ in range(n - 1)]
            durations.append(round(rng.uniform(HERO_MIN, SHOT_MAX), 2))
            mood = rng.choice(list(TEMPOS))
            sb = storyboard(durations).model_copy(
                update={"music": Music(mood=mood, bpm=rng.randint(*TEMPOS[mood]))})
            cut = cut_to_beat(sb, SHOT_MIN, SHOT_MAX, HERO_MIN)
            self.assertAlmostEqual(cut.duration, sb.duration, places=2)
            for shot in cut.shots[:-1]:
                self.assertGreaterEqual(shot.duration, SHOT_MIN - 1e-3, (durations, mood))
                self.assertLessEqual(shot.duration, SHOT_MAX + 1e-3, (durations, mood))
            self.assertGreaterEqual(cut.shots[-1].duration, HERO_MIN - 1e-3, (durations, mood))

    def test_cuts_land_on_the_chosen_tempo(self):
        sb = storyboard([3.0, 3.0, 3.5]).model_copy(update={"music": Music(mood="energetic", bpm=120)})
        beat = 60 / 120
        for start in cut_to_beat(sb, SHOT_MIN, SHOT_MAX, HERO_MIN).shot_starts():
            self.assertAlmostEqual(start / beat, round(start / beat), places=2)


class Loudness(unittest.TestCase):
    def test_every_mood_at_the_same_loudness_under_the_peak(self):
        for mood in SETTINGS:
            with self.subTest(mood=mood):
                bed = compose(mood, 8.0, 5.0)
                self.assertAlmostEqual(loudness(bed), LOUDNESS, delta=0.3)
                self.assertLessEqual(20 * np.log10(np.abs(bed).max()), PEAK + 0.01)

    def test_tempo_and_key_follow_the_director(self):
        bed = compose("calm", 6.0, 4.0, bpm=100, key=-3)
        self.assertEqual(bed.shape[1], 2)
        self.assertAlmostEqual(loudness(bed), LOUDNESS, delta=0.3)


class Choice(unittest.TestCase):
    def test_tempo_outside_the_moods_range_is_refused(self):
        with self.assertRaises(ValidationError):
            Music(mood="dark", bpm=130)
        Music(mood="energetic", bpm=130)

    def test_a_storyboard_without_music_falls_back_to_its_style(self):
        sb = storyboard().model_copy(update={"style": "bold_energetic"})
        self.assertEqual(mood_of(sb), "energetic")
        self.assertEqual(tempo_of(sb), ("energetic", SETTINGS["energetic"]["bpm"], 0))
        chosen = sb.model_copy(update={"music": Music(mood="warm", bpm=90, key=2)})
        self.assertEqual(tempo_of(chosen), ("warm", 90, 2))


if __name__ == "__main__":
    unittest.main()
