"""Muse Voice Transcribe: a recording to text, through the file endpoint.

    from pipeline.meta import voice
    voice.transcribe("brief.m4a")   # any format ffmpeg reads; converted to what the API takes

The endpoint takes WAV, mono, 16-bit PCM at 16 kHz, up to 10 minutes.
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from . import cache, client, config, usage


def _to_wav(source: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ac", "1", "-ar", "16000",
                        "-sample_fmt", "s16", str(wav)], check=True)
        return wav.read_bytes()


def transcribe(audio: Path | str, cache_ok: bool = True) -> str:
    """The recording's transcript."""
    wav = _to_wav(Path(audio))
    key = cache.request_key("voice.transcribe", {"model": config.VOICE, "audio": cache.digest(wav)})
    began = time.perf_counter()
    stored = cache.get_json(key, cache_ok)
    cached = stored is not None
    if not cached:
        settings = {"mode": "DIARIZATION", "model": config.VOICE, "audioEncoding": "WAV"}
        for attempt in range(client.MAX_RETRIES + 1):
            response = requests.post(f"{config.META_BASE_URL}/asr/transcribe",
                                     headers={"Authorization": f"Bearer {config.key('MODEL_API_KEY')}"},
                                     files={"request": (None, json.dumps(settings), "application/json"),
                                            "audio": ("audio.wav", wav, "audio/wav")},
                                     timeout=client.TIMEOUT_SECONDS)
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == client.MAX_RETRIES:
                break
            time.sleep(2 ** attempt)
        if not response.ok:
            raise client.MetaError(config.VOICE, response.text[:500], response.status_code)
        stored = response.json()
        cache.put_json(key, stored)
    seconds_of_audio = int(stored.get("audioDurationMs", 0) // 1000)
    usage.record(usage.Call(kind="transcribe", model=config.VOICE, cached=cached,
                            seconds=round(time.perf_counter() - began, 3), units=seconds_of_audio,
                            cost=0.0 if cached else seconds_of_audio * config.VOICE_PRICE_PER_SECOND))
    return stored.get("transcript", "")
