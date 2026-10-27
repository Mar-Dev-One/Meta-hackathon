"""Muse Voice Transcribe on a spoken brief, through the file endpoint.

Records nothing: give a WAV as the first argument, or it makes one with
Windows' built-in speech synthesizer. Either way ffmpeg converts it to what
the API accepts (WAV, mono, 16-bit PCM, 16 kHz)."""

import json
import subprocess
import sys
from pathlib import Path

import requests

from _common import META_BASE_URL, OUT, VOICE, key, report, save_json, timed

BRIEF = "Luxury perfume ad, dark and moody, fifteen seconds. End on the bottle with the brand name."


def synthesize(path: Path) -> None:
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{BRIEF}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def run(source: Path | None = None) -> dict:
    api_key = key("MODEL_API_KEY")
    if source is None:
        source = OUT / "06_brief_raw.wav"
        synthesize(source)
    wav = OUT / "06_brief_16k.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                    "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(wav)], check=True)

    settings = {"mode": "DIARIZATION", "model": VOICE, "audioEncoding": "WAV"}
    with timed() as t, wav.open("rb") as audio:
        response = requests.post(
            f"{META_BASE_URL}/asr/transcribe",
            headers={"Authorization": f"Bearer {api_key}"},
            files={
                "request": (None, json.dumps(settings), "application/json"),
                "audio": (wav.name, audio, "audio/wav"),
            },
            timeout=120,
        )
    if not response.ok:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
    body = response.json()
    save_json("06_voice_transcribe.json", body)
    return {"latency_s": t.seconds, "spoken": BRIEF if source.name == "06_brief_raw.wav" else str(source),
            "transcript": body.get("transcript"), "audio_ms": body.get("audioDurationMs")}


if __name__ == "__main__":
    report(run(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
