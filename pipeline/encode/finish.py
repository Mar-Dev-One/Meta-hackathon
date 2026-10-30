"""The last pass over a rendered video, with ffmpeg: the whole ad faded from
and to black, and dipped to black at the cuts that ask for it. Titles aren't
added here: the Studio draws them into the frames (text.*), where the
critic can see them.
"""

import json
import subprocess
from pathlib import Path

DIP = 0.7        # seconds a dip to black takes, half out before its cut and half in after
DISSOLVE = 0.8   # seconds the film takes to dissolve into the end card, before the film's end


def probe(video: Path) -> dict:
    """width, height and duration (seconds) of a video."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", str(video)],
                         check=True, capture_output=True, text=True).stdout
    info = json.loads(out)
    stream = info["streams"][0]
    return {"width": stream["width"], "height": stream["height"], "duration": float(info["format"]["duration"])}


def dips(times: list[float], length: float = DIP) -> str | None:
    """An ffmpeg `eq` filter that dips the picture to black at each of
    `times`: its brightness multiplied by a factor that falls to 0 at the
    cut and rises back over `length` (eq's contrast f with brightness
    (f - 1) / 2 is the picture times f; saturation f takes the colour down
    with it)."""
    if not times:
        return None
    half = length / 2
    factor = "*".join(f"min(1,abs(t-{t:.3f})/{half:.3f})" for t in times)
    return f"eq=eval=frame:contrast='{factor}':brightness='({factor}-1)/2':saturation='{factor}'"


def finish(video_in: Path, video_out: Path, fade_in: float = 0.5, fade_out: float = 0.8,
           audio: Path | None = None, dip_at: list[float] = (), end_card: Path | None = None,
           card_seconds: float = 0.0, fps: int = 30) -> Path:
    """Writes video_in faded in and out to video_out (H.264, yuv420p, CRF 16),
    dipped to black at the times in `dip_at` (cuts that ask for it), ending
    on `end_card` (a still, `card_seconds` long after the film, dissolved
    into over DISSOLVE seconds before the film ends), with `audio`
    (pipeline.encode.music) as its sound if given: cut to the picture, faded
    out with it (a little longer, so the sound outlasts the image by a
    breath) and in over a few frames, AAC 192 kb/s. The music plays on
    through a dip and under the card."""
    film = probe(video_in)["duration"]
    card = card_seconds if end_card else 0.0
    duration = film + card
    inputs = ["-i", str(video_in)]
    chain = [f"[0:v]fps={fps},setsar=1,format=yuv420p" + "".join(f",{f}" for f in [dips(list(dip_at))] if f) + "[film]"]
    picture = "film"
    if end_card:
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{card + DISSOLVE:.3f}", "-i", str(end_card)]
        chain += [f"[1:v]fps={fps},setsar=1,format=yuv420p[card]",
                  f"[film][card]xfade=transition=fade:duration={DISSOLVE}:offset={film - DISSOLVE:.3f}[joined]"]
        picture = "joined"
    fades = []
    if fade_in > 0:
        fades.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        fades.append(f"fade=t=out:st={max(duration - fade_out, 0):.3f}:d={fade_out}")
    chain.append(f"[{picture}]" + (",".join(fades) or "null") + "[out]")
    maps = ["-map", "[out]"]
    if audio:
        inputs += ["-i", str(audio)]
        sound_out = min(1.5 * fade_out, duration)
        chain.append(f"[{2 if end_card else 1}:a]afade=t=in:st=0:d=0.08,"
                     f"afade=t=out:st={duration - sound_out:.3f}:d={sound_out:.3f}[sound]")
        maps += ["-map", "[sound]", "-c:a", "aac", "-b:a", "192k"]
    command = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(chain), *maps,
               "-t", f"{duration:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(video_out)]
    subprocess.run(command, check=True)
    return video_out
