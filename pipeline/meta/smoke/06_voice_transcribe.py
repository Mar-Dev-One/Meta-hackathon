"""Muse Voice Transcribe on a spoken brief. Give a recording as the first
argument (any format ffmpeg reads), or it makes one with Windows' built-in
speech synthesizer."""

import subprocess
import sys
from pathlib import Path

from _common import OUT, report

from pipeline.meta import voice

BRIEF = "Luxury perfume ad, dark and moody, fifteen seconds. End on the bottle with the brand name."


def synthesize(path: Path) -> None:
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{path}'); $s.Speak('{BRIEF}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def run(source: Path | None = None) -> dict:
    spoken = str(source) if source else BRIEF
    if source is None:
        source = OUT / "06_brief.wav"
        if not source.exists():   # the same recording each run, so the cache can answer
            synthesize(source)
    return {"spoken": spoken, "transcript": voice.transcribe(source)}


if __name__ == "__main__":
    report(run(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
