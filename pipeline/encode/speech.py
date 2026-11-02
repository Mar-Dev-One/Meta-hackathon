"""The voice-over's sound: each line spoken by Meta's MMS-TTS (facebook/mms-tts-eng,
CC BY-NC 4.0), run locally on the CPU (the Meta Model API has no text to speech),
placed at its time on a track as long as the ad, and mixed over the music, which
ducks under the voice.

MMS reads only plain lowercase letters: punctuation is dropped, so a line is
spoken phrase by phrase with a short pause where its punctuation was; accents
are taken off; numbers must come as words. Needs pipeline/requirements-voice.txt.

    audio = speak("Some evenings ask for nothing but a little light.")   # 16 kHz mono, cached
    track([(0.8, audio)], 12.5, Path("voice.wav"))
    duck(Path("music.wav"), Path("voice.wav"), Path("mix.wav"))
"""

import hashlib
import io
import re
import subprocess
import unicodedata
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from pipeline.meta import config

from .music import RATE, loudness, write_wav

MODEL = "facebook/mms-tts-eng"
SPEECH_RATE = 16000       # MMS speaks at 16 kHz
PACE = 0.92               # its speaking rate (1 is its own): a little slower reads clearer
PAUSE = 0.28              # seconds of silence where a line's punctuation was
LOUDNESS = -15.0          # LUFS of the speech itself: a little over the music's -16, which ducks under it
CACHE = config.CACHE_DIR / "speech"

_tts = None   # (model, tokenizer), loaded once


class VoiceUnavailable(RuntimeError):
    """MMS-TTS can't run here: its packages aren't installed."""


def _load():
    global _tts
    if _tts is None:
        try:
            import torch  # noqa: F401
            from transformers import AutoTokenizer, VitsModel
        except ImportError as e:
            raise VoiceUnavailable("the voice-over needs torch and transformers: "
                                   "pip install -r pipeline/requirements-voice.txt") from e
        model = VitsModel.from_pretrained(MODEL)
        model.speaking_rate = PACE
        _tts = model, AutoTokenizer.from_pretrained(MODEL)
    return _tts


def phrases(text: str) -> list[str]:
    """A line as MMS can read it: its phrases (split where punctuation was),
    accents off, lowercase, only letters, apostrophes and hyphens."""
    out = []
    for part in re.split(r"[.,;:!?()\"—–…]+|\s-\s", text):   # split first: dashes aren't ASCII
        plain = unicodedata.normalize("NFKD", part).encode("ascii", "ignore").decode()
        words = re.sub(r"[^a-z' -]+", " ", plain.lower())
        words = re.sub(r"\s+", " ", words).strip(" -'")
        if words:
            out.append(words)
    return out


def speak(text: str) -> np.ndarray:
    """The line spoken (float32 mono at SPEECH_RATE), phrase by phrase with
    PAUSE between; cached on disk by its text and the voice's settings."""
    parts = phrases(text)
    if not parts:
        return np.zeros(0, np.float32)
    key = hashlib.sha256(repr((MODEL, PACE, PAUSE, parts)).encode()).hexdigest()
    cached = CACHE / f"{key}.wav"
    if cached.exists():
        with wave.open(str(cached), "rb") as w:
            return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32767
    import torch

    model, tokenizer = _load()
    gap = np.zeros(round(PAUSE * SPEECH_RATE), np.float32)
    pieces = []
    for i, part in enumerate(parts):
        torch.manual_seed(0)   # VITS samples its rhythm: the same line sounds the same every time
        with torch.no_grad():
            pieces += ([gap] if i else []) + [model(**tokenizer(part, return_tensors="pt")).waveform[0].numpy()]
    audio = np.concatenate(pieces).astype(np.float32)
    CACHE.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SPEECH_RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    cached.write_bytes(buffer.getvalue())
    return audio


def seconds(audio: np.ndarray) -> float:
    return len(audio) / SPEECH_RATE


def track(lines: list[tuple[float, np.ndarray]], length: float, out: Path) -> Path:
    """The spoken lines (start, audio) on a stereo track `length` seconds long
    at the music's rate, the speech brought to LOUDNESS: a line starts at
    its time, or just after the one before ends; past the end it is faded
    out (the lines' checks keep that rare)."""
    n = round(length * RATE)
    voice = np.zeros(n, np.float32)
    spoken = [resample_poly(audio, RATE // SPEECH_RATE, 1).astype(np.float32) for _, audio in lines]
    if spoken:
        level = loudness(np.stack([np.concatenate(spoken)] * 2, axis=1))
        gain = 10 ** ((LOUDNESS - level) / 20)
        free = 0
        for (start, _), audio in zip(lines, spoken):
            at = max(round(start * RATE), free)
            piece = audio[:max(n - at, 0)] * gain
            if len(piece) < len(audio):   # cut by the end: faded, not clipped
                fade = min(len(piece), round(0.15 * RATE))
                piece[len(piece) - fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            voice[at:at + len(piece)] += piece
            free = at + len(audio) + round(0.25 * RATE)
        peak = np.abs(voice).max()
        if peak > 0.9:
            voice *= 0.9 / peak
    return write_wav(np.stack([voice, voice], axis=1), out)


def duck(music: Path, voice: Path, out: Path) -> Path:
    """The music and the voice as one track: the music pressed down under the
    voice (sidechain compression: it dips while a line is spoken and comes
    back between lines), the voice over it, the peaks held under 0 dBFS."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(music), "-i", str(voice), "-filter_complex",
                    "[1:a]asplit=2[voice][key];"
                    # about 7 dB down under a line (measured on LUMEN's music): under, not gone
                    "[0:a][key]sidechaincompress=threshold=0.05:ratio=4:attack=30:release=450:makeup=1[bed];"
                    "[bed][voice]amix=inputs=2:normalize=0,alimiter=limit=0.95[out]",
                    "-map", "[out]", "-ar", str(RATE), "-ac", "2", str(out)], check=True)
    return out
