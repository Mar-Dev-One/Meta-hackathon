"""The last pass over a rendered video, with ffmpeg: titles faded in and out
over the picture, and the whole thing faded from and to black.

Titles are drawn by ffmpeg until the Studio renders text itself
(docs/ROADMAP.md, Phase 1.7); then they move into the frame, where the
critic can see them.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# A system font for now; the shipped demos switch to OFL fonts in Assets/fonts.
DEFAULT_FONT = Path("C:/Windows/Fonts/georgia.ttf")


@dataclass
class Title:
    text: str
    start: float           # seconds
    end: float
    size: float = 0.08     # text height as a fraction of the frame's height
    y: float = 0.5         # the text's centre, 0 = top, 1 = bottom
    color: str = "white"
    fade: float = 0.6      # seconds in and out
    tracking: int = 0      # hair spaces between letters: wide, "luxury" lettering
    font: Path = DEFAULT_FONT


def probe(video: Path) -> dict:
    """width, height and duration (seconds) of a video."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(video)],
                         check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    return {"width": stream["width"], "height": stream["height"], "duration": float(info["format"]["duration"])}


def _escape(text: str) -> str:
    """Text for a drawtext value inside single quotes in a filtergraph."""
    return text.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")


def _font_path(font: Path) -> str:
    # The filtergraph's own escaping: a Windows drive's colon must be escaped.
    return str(font).replace("\\", "/").replace(":", "\\:")


def _drawtext(title: Title, height: int) -> str:
    text = ("\u200a" * title.tracking).join(title.text) if title.tracking else title.text
    s, e, f = title.start, title.end, max(title.fade, 1e-3)
    alpha = f"if(lt(t,{s}),0,if(lt(t,{s + f}),(t-{s})/{f},if(lt(t,{e - f}),1,if(lt(t,{e}),({e}-t)/{f},0))))"
    return (f"drawtext=fontfile='{_font_path(title.font)}':text='{_escape(text)}'"
            f":fontsize={round(title.size * height)}:fontcolor={title.color}"
            f":x=(w-text_w)/2:y=h*{title.y}-text_h/2:alpha='{alpha}'")


def finish(video_in: Path, video_out: Path, titles: list[Title] = (), fade_in: float = 0.5,
           fade_out: float = 0.8) -> Path:
    """Writes video_in with titles and fades to video_out (H.264, yuv420p, CRF 16)."""
    info = probe(video_in)
    filters = [_drawtext(t, info["height"]) for t in titles]
    if fade_in > 0:
        filters.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        filters.append(f"fade=t=out:st={max(info['duration'] - fade_out, 0)}:d={fade_out}")

    command = ["ffmpeg", "-y", "-v", "error", "-i", str(video_in)]
    if filters:
        command += ["-vf", ",".join(filters)]
    command += ["-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video_out)]
    subprocess.run(command, check=True)
    return video_out
