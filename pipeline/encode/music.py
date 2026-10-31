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
hero shot (the last one), and everything settles into the final chord. The
mix: the pads and bass pumped by the kick (energetic), everything in a
synthesized stereo room (a convolution reverb), warmed by soft saturation,
and brought to one loudness (LOUDNESS, BS.1770), so every mood plays as loud.
"""

import subprocess
import wave
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve, lfilter

from pipeline.schemas import Storyboard

RATE = 48000
MUSIC_DIR = Path(__file__).resolve().parents[2] / "Assets" / "music"
TRACK_TYPES = (".wav", ".mp3", ".m4a", ".flac")
LOUDNESS = -16.0   # LUFS: a music bed for the web, under the picture
PEAK = -1.0        # dB: the highest sample after the soft limit

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
    """The storyboard's music's mood: the director's choice, or (a storyboard
    without one) the mood whose names and words come up most in its style
    and title, "calm" when none do."""
    if sb.music:
        return sb.music.mood
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
        x = lfilter([1 - a], [1, -a], x)
    return x


def _highpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    return x - _lowpass(x, cutoff)


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


def open_hat(seconds: float = 0.3, seed: int = 0) -> np.ndarray:
    t = _t(seconds)
    return _highpass(np.random.default_rng(seed).uniform(-1, 1, len(t)), 6000) * np.exp(-12 * t)


def clap(seconds: float = 0.25, seed: int = 0) -> np.ndarray:
    """Band-passed noise in three quick bursts and a tail, over a short tone: a clap-snare."""
    t = _t(seconds)
    noise = _highpass(_lowpass(np.random.default_rng(seed).uniform(-1, 1, len(t)), 3500), 900)
    bursts = sum(np.exp(-200 * np.clip(t - d, 0, None)) * (t >= d) for d in (0.0, 0.011, 0.022))
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-30 * t)
    return 1.6 * noise * (bursts + 0.6 * np.exp(-18 * t)) + 0.35 * body


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


def _room(seconds: float, seed: int) -> np.ndarray:
    """A room's impulse response: noise dying away over `seconds`, its highs
    sooner (as a real room's do), after a short gap (the first reflections)."""
    t = _t(seconds)
    noise = np.random.default_rng(seed).normal(0, 1, len(t))
    tail = 0.6 * noise * np.exp(-6.9 * t / seconds) + 0.4 * _lowpass(noise, 3000) * np.exp(-4 * t / seconds)
    tail[:int(0.012 * RATE)] = 0
    return tail / np.sqrt((tail ** 2).sum())


def _reverb(x: np.ndarray, seconds: float, mix: float) -> np.ndarray:
    """`x` (mono) in a stereo room: two different rooms' tails, one per side, under the dry sound (n x 2)."""
    rooms = [fftconvolve(x, _room(seconds, seed))[:len(x)] for seed in (1, 2)]
    return np.stack([x + mix * r for r in rooms], axis=1)


def _pump(n: int, hits: list[float], beat: float, depth: float) -> np.ndarray:
    """A gain that ducks at each kick and swells back within the beat: the sidechain pump."""
    gain = np.ones(n)
    length = int(0.8 * beat * RATE)
    shape = 1 - depth * (1 - np.sin(np.linspace(0, np.pi / 2, length)) ** 2)
    for at in hits:
        i = int(at * RATE)
        k = min(length, n - i)
        if k > 0:
            gain[i:i + k] = np.minimum(gain[i:i + k], shape[:k])
    return gain


def loudness(stereo: np.ndarray) -> float:
    """Integrated loudness in LUFS (BS.1770's K-weighting at 48 kHz; no gating: a bed has no silences)."""
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585],
                stereo, axis=0)
    y = lfilter([1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621], y, axis=0)
    return -0.691 + 10 * np.log10(max((y ** 2).mean(0).sum(), 1e-12))


def master(stereo: np.ndarray) -> np.ndarray:
    """Warmed by soft saturation, at LOUDNESS, its peaks held under PEAK by a soft limit."""
    x = np.tanh(1.5 * stereo / (np.abs(stereo).max() or 1.0)) / np.tanh(1.5)
    ceiling = 10 ** (PEAK / 20)
    knee = 0.7 * ceiling   # above it, peaks bend smoothly towards the ceiling
    for _ in range(4):     # the limit lowers loudness a little: settle on the target
        x = x * 10 ** ((LOUDNESS - loudness(x)) / 20)
        over = np.abs(x) > knee
        x = np.where(over, np.sign(x) * (knee + (ceiling - knee) * np.tanh((np.abs(x) - knee) / (ceiling - knee))), x)
    return x


# --- The bed ------------------------------------------------------------------------------


def tempo_of(sb: Storyboard) -> tuple[str, int, int]:
    """The storyboard's music: (mood, bpm, key), the director's or the mood's own."""
    if sb.music:
        return sb.music.mood, sb.music.bpm, sb.music.key
    mood = mood_of(sb)
    return mood, SETTINGS[mood]["bpm"], 0


def compose(mood: str, seconds: float, hero: float, bpm: int | None = None, key: int = 0) -> np.ndarray:
    """The music for an ad of `seconds`, its hero shot starting at `hero`
    seconds, at `bpm` (the mood's own if None), `key` semitones from the
    mood's home key: stereo float samples (n x 2), at LOUDNESS."""
    s = dict(SETTINGS[mood], chords=[[n + key for n in c] for c in SETTINGS[mood]["chords"]])
    beat = 60.0 / (bpm or s["bpm"])
    bar = 4 * beat
    total = seconds + 1.0   # a tail, cut by the fade
    track = np.zeros(int(total * RATE))
    side = np.zeros_like(track)          # what's spread out to the sides (the pads), for width
    low = np.zeros_like(track)           # the bass: pumped with the pads, kept dry
    kicks = []
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
                at = start + k * beat
                if landing - beat / 2 < at + beat and at < landing:   # a breath before the hit
                    continue
                _place(track, kick(), at, 0.6)
                kicks.append(at)
                _place(track, hat(seed=b * 4 + k), at + beat / 2, 0.2)
                _place(low, bass(root - 12, beat / 2 * 0.9), at + beat / 2, 0.35)
                if k % 2:
                    _place(track, clap(seed=b * 4 + k), at, 0.3)
                if k == 3:
                    _place(track, open_hat(seed=b), at + beat / 2, 0.12)
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

    if kicks:   # the pads and bass breathe with the kick
        pump = _pump(len(track), kicks + [landing], beat, 0.6)
        side, low = side * pump, low * pump
    side = _echo(side, 0.75 * beat, 0.3, 0.25)
    room = {"dark": 2.8, "calm": 2.2, "energetic": 1.2, "warm": 1.6}[mood]
    stereo = _reverb(side, room, 0.5) + _reverb(track, room, 0.15) + low[:, None]
    return master(stereo)


def write_wav(samples: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


def cut_to_beat(sb: Storyboard, shortest: float, longest: float, hero_shortest: float,
                mood: str | None = None) -> Storyboard:
    """The storyboard with its cuts moved onto the music's beats (the
    nearest beat each, within a beat; the hero's onto a bar line when one is
    that close), so the picture cuts with the music; its length the same,
    every shot still `shortest`-`longest` seconds (the hero at least
    `hero_shortest`). What happens inside a shot (titles, light keys) moves
    with it. Unchanged when the music is a track from Assets/music: its
    beats aren't known."""
    chosen, bpm, _ = tempo_of(sb)
    mood = mood or chosen
    if track_for(mood):
        return sb
    beat = 60.0 / (bpm if mood == chosen else SETTINGS[mood]["bpm"])
    bar = 4 * beat
    starts, total = sb.shot_starts(), sb.duration
    new = [0.0]
    def nearest(s: float, step: float) -> list[float]:
        return sorted((round(np.floor(s / step) * step, 3), round(np.ceil(s / step) * step, 3)), key=lambda t: abs(t - s))

    for i, s in enumerate(starts[1:], 1):
        hero = i == len(starts) - 1
        # The cut's window: the shot before it long enough, and room after it for every shot left (the hero last).
        lo = new[-1] + shortest
        hi = total - hero_shortest - shortest * (len(starts) - 1 - i)
        options = (nearest(s, bar) if hero else []) + nearest(s, beat)   # the hero: a bar line first
        fits = [t for t in options if abs(t - s) <= beat and lo - 1e-6 <= t <= hi + 1e-6 and t - new[-1] <= longest]
        # No beat fits: the cut stays where it was, moved only as far as its window needs.
        new.append(fits[0] if fits else round(min(max(s, lo), hi) if lo <= hi else s, 3))
    moved = [n - o for n, o in zip(new, starts)]

    def shift(t: float) -> float:
        i = max(k for k, s in enumerate(starts) if s <= t + 1e-9)
        return round(min(max(t + moved[i], 0.0), total), 3)

    data = sb.model_dump(by_alias=True, exclude_none=True)
    for shot, a, b in zip(data["shots"], new, new[1:] + [total]):
        shot["duration"] = round(b - a, 3)
    for title in data.get("titles", []):
        title["start"] = shift(title["start"])
    for track in data.get("tracks", []):
        keys = {}
        for key in track["keys"]:
            keys[shift(key["t"])] = key | {"t": shift(key["t"])}   # one key per time, the later one kept
        track["keys"] = sorted(keys.values(), key=lambda k: k["t"])
    return Storyboard.model_validate(data)


def track_for(mood: str) -> Path | None:
    """A music file for the mood in Assets/music, if there is one."""
    for kind in TRACK_TYPES:
        path = MUSIC_DIR / f"{mood}{kind}"
        if path.exists():
            return path
    return None


def music_for(sb: Storyboard, out: Path, mood: str | None = None) -> Path:
    """The storyboard's music as a WAV at `out`, as long as the ad (its end
    card too): a track from Assets/music when there's one for its mood, else
    synthesized, at the storyboard's tempo and key."""
    chosen, bpm, key = tempo_of(sb)
    if mood and mood != chosen:
        bpm, key = None, 0
    return music(mood or chosen, sb.length, sb.shot_starts()[-1], out, bpm=bpm, key=key)


def music(mood: str, seconds: float, hero: float, out: Path, bpm: int | None = None, key: int = 0) -> Path:
    """Music in `mood` as a WAV at `out`, `seconds` long, lifting at `hero`
    (the last shot's start): a track from Assets/music when there's one for
    the mood, else synthesized."""
    track = track_for(mood)
    if track:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(track), "-t", f"{seconds:.3f}",
                        "-ar", str(RATE), "-ac", "2", str(out)], check=True)
        return out
    return write_wav(compose(mood, seconds, hero, bpm, key), out)
