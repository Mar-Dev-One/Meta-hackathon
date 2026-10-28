"""The last pass over a rendered video, with ffmpeg: the whole ad faded from
and to black. Titles aren't added here: the Studio draws them into the
frames (text.*), where the critic can see them.
"""

import json
import subprocess
from pathlib import Path


def probe(video: Path) -> dict:
    """width, height and duration (seconds) of a video."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(video)],
                         check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    return {"width": stream["width"], "height": stream["height"], "duration": float(info["format"]["duration"])}


def finish(video_in: Path, video_out: Path, fade_in: float = 0.5, fade_out: float = 0.8) -> Path:
    """Writes video_in faded in and out to video_out (H.264, yuv420p, CRF 16)."""
    filters = []
    if fade_in > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        filters.append(f"fade=t=out:st={max(probe(video_in)['duration'] - fade_out, 0)}:d={fade_out}")

    command = ["ffmpeg", "-y", "-v", "error", "-i", str(video_in)]
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video_out)]
    subprocess.run(command, check=True)
    return video_out
