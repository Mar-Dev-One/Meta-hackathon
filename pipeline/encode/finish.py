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


def finish(video_in: Path, video_out: Path, fade_in: float = 0.5, fade_out: float = 0.8,
           audio: Path | None = None) -> Path:
    """Writes video_in faded in and out to video_out (H.264, yuv420p, CRF 16),
    with `audio` (pipeline.encode.music) as its sound if given: cut to the
    picture, faded out with it (a little longer, so the sound outlasts the
    image by a breath) and in over a few frames, AAC 192 kb/s."""
    duration = probe(video_in)["duration"]
    filters = []
    if fade_in > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        filters.append(f"fade=t=out:st={max(duration - fade_out, 0)}:d={fade_out}")

    command = ["ffmpeg", "-y", "-v", "error", "-i", str(video_in)]
    if audio:
        command += ["-i", str(audio)]
    if filters:
        command += ["-vf", ",".join(filters)]
    if audio:
        sound_out = min(1.5 * fade_out, duration)
        command += ["-af", f"afade=t=in:st=0:d=0.08,afade=t=out:st={duration - sound_out:.3f}:d={sound_out:.3f}",
                    "-map", "0:v:0", "-map", "1:a:0", "-t", f"{duration:.3f}", "-c:a", "aac", "-b:a", "192k"]
    command += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video_out)]
    subprocess.run(command, check=True)
    return video_out
