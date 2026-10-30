"""The ad's music: a bed in the style's mood, cut to the ad's length, that
swells into the hero shot and fades out with the picture.

    wav = music_for(sb, run.path("final", "music.wav"))     # then finish(..., audio=wav)

A track at Assets/music/<mood>.wav (or .mp3, .m4a, .flac) is used when
there is one, cut and faded to length by ffmpeg: drop licensed music there.
Otherwise the bed is synthesized here, note by note with numpy, so it's
original and needs no licence:

    dark        slow minor pads over a sub drone, a heartbeat pulse    (luxury, moody, sleek)
    calm        soft major pads and a plucked arpeggio                 (clean, minimal, soft)
    energetic   four on the floor, offbeat hats, a bass line, stabs    (bold, neon, playful)
    warm        electric-piano chords with tremolo, a soft shaker      (natural, organic, glowing)

Bars are laid from the start; a rising swell lands on the first beat of the
hero shot (the last one), and everything settles into the final chord.
"""

import subprocess
import wave
from pathlib import Path

import numpy as np

from pipeline.schemas import Storyboard

RATE = 48000
MUSIC_DIR = Path(__file__).resolve().parents[2] / "Assets" / "music"
TRACK_TYPES = (".wav", ".mp3", ".m4a", ".flac")

# The style library's names and the words a brief's style uses, by mood.
MOODS = {
    "dark": ("luxury_dark", "tech_sleek", "dark", "moody", "luxury", "noir", "sleek", "dramatic"),
    "energetic": ("bold_energetic", "playful_pop", "bold", "energetic", "neon", "fast", "playful", "pop", "loud"),
    "warm": ("natural_organic", "warm_glow", "warm", "natural", "organic", "earthy", "glow", "honest"),
    "calm": ("clean_minimal", "soft_pastel", "clean", "minimal", "calm", "soft", "pastel", "bright", "airy"),
}

# Per mood: beats per minute, the chords (MIDI notes, one per bar, looped) and its parts.
SETTINGS = {
    "dark": dict(bpm=68, chords=[[45, 52, 57, 60], [41, 48, 53, 57], [38, 45, 50, 53], [40, 47, 52, 56]]),
    "calm": dict(bpm=88, chords=[[48, 55, 60, 64], [45, 52, 57, 60], [41, 48, 53, 57], [43, 50, 55, 59]]),
    "energetic": dict(bpm=124, chords=[[45, 52, 57, 60], [41, 48, 53, 57], [48, 55, 60, 64], [43, 50, 55, 59]]),
    "warm": dict(bpm=82, chords=[[41, 48, 53, 57, 60], [46, 53, 58, 62], [43, 50, 55, 58], [48, 55, 60, 64]]),
}


def mood_of(sb: Storyboard) -> str:
    """The mood whose names and words come up most in the storyboard's style
    (and title): "calm" when none do."""
    text = f"{sb.style} {sb.title}".lower()
    found = {mood: sum(word in text for word in words) for mood, words in MOODS.items()}
    best = max(found, key=found.get)
    return best if found[best] else "calm"


# --- Instruments --------------------------------------------------------------------------


def _hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE)) / RATE


def _envelope(n: int, attack: float, release: float) -> np.ndarray:
    """A linear attack and release over `n` samples, flat between."""
    env = np.ones(n)
    a, r = min(int(attack * RATE), n // 2), min(int(release * RATE), n // 2)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if r:
        env[-r:] *= np.linspace(1, 0, r)
    return env


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """One-pole low-pass (soft, warm), run twice for 12 dB per octave."""
    a = np.exp(-2 * np.pi * cutoff / RATE)
    for _ in range(2):
        y = np.empty_like(x)
        acc = 0.0
        for i, v in enumerate(x):   # fine at these lengths (a few seconds per voice)
            acc = (1 - a) * v + a * acc
            y[i] = acc
        x = y
    return x


def pad(notes: list[int], seconds: float, brightness: float = 900.0) -> np.ndarray:
    """Detuned saws, low-passed, slow in and out: a string-machine pad."""
    t = _t(seconds)
    out = np.zeros_like(t)
    for note in notes:
        for detune in (-0.08, 0.0, 0.08):
            phase = (_hz(note + detune) * t) % 1.0
            out += 2 * phase - 1
    out = _lowpass(out / (3 * len(notes)), brightness)
    return out * _envelope(len(t), 0.6 * seconds, 0.4 * seconds)


def epiano(notes: list[int], seconds: float) -> np.ndarray:
    """Sines with a bell-like second partial, a quick attack, a slow decay and tremolo."""
    t = _t(seconds)
    out = sum(np.sin(2 * np.pi * _hz(n) * t) + 0.25 * np.sin(2 * np.pi * 2 * _hz(n) * t) * np.exp(-6 * t)
              for n in notes)
    out = out / len(notes) * np.exp(-1.2 * t) * (1 + 0.25 * np.sin(2 * np.pi * 4.5 * t))
    return out * _envelope(len(t), 0.005, 0.2)


def pluck(note: int, seconds: float) -> np.ndarray:
    """A plucked string (Karplus-Strong): bright, then dark."""
    n, period = int(seconds * RATE), max(2, int(RATE / _hz(note)))
    rng = np.random.default_rng(note)
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = 0.5 * (buf[i % period] + buf[(i + 1) % period]) * 0.996
    return out * _envelope(n, 0.002, 0.05)


def kick(seconds: float = 0.4) -> np.ndarray:
    t = _t(seconds)
    pitch = 50 + 90 * np.exp(-25 * t)
    return np.sin(2 * np.pi * np.cumsum(pitch) / RATE) * np.exp(-7 * t)


def hat(seconds: float = 0.08, seed: int = 0) -> np.ndarray:
    t = _t(seconds)
    noise = np.random.default_rng(seed).uniform(-1, 1, len(t))
    return np.diff(noise, prepend=0) * np.exp(-60 * t)


def shaker(seconds: float = 0.12, seed: int = 0) -> np.ndarray:
    t = _t(seconds)
    return np.random.default_rng(seed).uniform(-1, 1, len(t)) * np.sin(np.pi * t / seconds) ** 2


def bass(note: int, seconds: float) -> np.ndarray:
    t = _t(seconds)
    phase = (_hz(note) * t) % 1.0
    return _lowpass(np.sign(phase - 0.5) * 0.6 + (2 * phase - 1) * 0.4, 350) * _envelope(len(t), 0.004, 0.06)


def sub(note: int, seconds: float) -> np.ndarray:
    t = _t(seconds)
    return np.sin(2 * np.pi * _hz(note) * t) * _envelope(len(t), 1.0, 1.0)


def swell(seconds: float) -> np.ndarray:
    """Filtered noise rising into a hit: the lead-in to the hero shot."""
    t = _t(seconds)
    noise = np.random.default_rng(7).uniform(-1, 1, len(t))
    return _lowpass(noise, 2500) * (t / seconds) ** 3


def _place(track: np.ndarray, sound: np.ndarray, at: float, gain: float) -> None:
    i = int(at * RATE)
    if i >= len(track):
        return
    n = min(len(sound), len(track) - i)
    track[i:i + n] += gain * sound[:n]


def _echo(x: np.ndarray, delay: float, feedback: float, mix: float) -> np.ndarray:
    """A feedback delay: a sense of space."""
    d = int(delay * RATE)
    wet = np.zeros_like(x)
    for k in range(1, 6):
        if k * d >= len(x):
            break
        wet[k * d:] += x[:-k * d] * feedback ** k
    return x + mix * wet


# --- The bed ------------------------------------------------------------------------------


def compose(mood: str, seconds: float, hero: float) -> np.ndarray:
    """The music for an ad of `seconds`, its hero shot starting at `hero`
    seconds: stereo float samples (n x 2), peaking at -3 dB."""
    s = SETTINGS[mood]
    beat = 60.0 / s["bpm"]
    bar = 4 * beat
    total = seconds + 1.0   # a tail, cut by the fade
    track = np.zeros(int(total * RATE))
    side = np.zeros_like(track)          # what's spread out to the sides (the pads), for width
    bars = int(np.ceil(total / bar))
    # The hero lands on a downbeat: the last bar line at or after its start, if close; else its start.
    landing = hero if (np.ceil(hero / bar) * bar - hero) > beat else np.ceil(hero / bar) * bar

    for b in range(bars):
        start = b * bar
        chord = s["chords"][b % len(s["chords"])]
        if start >= landing - 1e-6:
            chord = s["chords"][0]       # the hero sits on the home chord
        root = chord[0]
        if mood == "dark":
            _place(side, pad(chord, bar + 0.8, 700), start, 0.5)
            _place(track, sub(root - 12, bar + 0.5), start, 0.35)
            for k in (0, 2):              # a heartbeat on beats 1 and 3
                _place(track, kick(0.5), start + k * beat, 0.35)
                _place(track, kick(0.4), start + k * beat + 0.18, 0.18)
        elif mood == "calm":
            _place(side, pad(chord, bar + 0.8, 1400), start, 0.4)
            for k in range(8):            # eighth-note arpeggio
                _place(track, pluck(chord[k % len(chord)] + 12, beat), start + k * beat / 2, 0.22)
        elif mood == "energetic":
            for k in range(4):
                _place(track, kick(), start + k * beat, 0.6)
                _place(track, hat(seed=b * 4 + k), start + k * beat + beat / 2, 0.25)
                _place(track, bass(root - 12, beat / 2 * 0.9), start + k * beat + beat / 2, 0.35)
            for k in (0, 1.5, 3):          # off-kilter chord stabs
                _place(side, pad(chord, beat * 0.45, 2500) * 2.2, start + k * beat, 0.35)
        else:  # warm
            _place(side, epiano(chord, bar), start, 0.4)
            _place(track, sub(root - 12, bar), start, 0.2)
            for k in range(8):
                _place(track, shaker(seed=b * 8 + k), start + k * beat / 2, 0.06 if k % 2 else 0.1)

    lead = min(2 * beat, landing)
    _place(track, swell(lead), landing - lead, 0.25 if mood != "energetic" else 0.35)
    _place(track, kick(0.6), landing, 0.5)                         # the hit on the hero
    _place(side, pad(s["chords"][0], 3.0, 1800), landing, 0.35)    # the home chord, held

    side = _echo(side, 0.75 * beat, 0.35, 0.4)
    gap = int(0.012 * RATE)   # the sides 12 ms later on the right: width without phase trouble in mono
    stereo = np.stack([track + side, track + np.concatenate([np.zeros(gap), side[:-gap]])], axis=1)
    peak = np.abs(stereo).max() or 1.0
    return stereo / peak * 10 ** (-3 / 20)


def write_wav(samples: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


def track_for(mood: str) -> Path | None:
    """A music file for the mood in Assets/music, if there is one."""
    for kind in TRACK_TYPES:
        path = MUSIC_DIR / f"{mood}{kind}"
        if path.exists():
            return path
    return None


def music_for(sb: Storyboard, out: Path, mood: str | None = None) -> Path:
    """The storyboard's music as a WAV at `out`, as long as the ad: a track
    from Assets/music when there's one for its mood, else synthesized."""
    return music(mood or mood_of(sb), sb.duration, sb.shot_starts()[-1], out)


def music(mood: str, seconds: float, hero: float, out: Path) -> Path:
    """Music in `mood` as a WAV at `out`, `seconds` long, lifting at `hero`
    (the last shot's start): a track from Assets/music when there's one for
    the mood, else synthesized."""
    track = track_for(mood)
    if track:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(track), "-t", f"{seconds:.3f}",
                        "-ar", str(RATE), "-ac", "2", str(out)], check=True)
        return out
    return write_wav(compose(mood, seconds, hero), out)
