"""The voice-over: a few short lines Muse Spark writes for the finished
storyboard, timed to its shots, checked in code (each fits its time at the
voice's pace, the brand's name in the last, numbers as words), then spoken
by MMS-TTS (pipeline.encode.speech) onto a track as long as the ad. Optional
(make_ad's `voice`): if it can't be written or spoken, the ad is made without.

    path = voiceover(run, sb, brief, profile)   # final/voice.wav, or None
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from pipeline.encode import speech
from pipeline.meta import spark
from pipeline.runs import Run
from pipeline.schemas import BrandProfile, Storyboard

WORDS_PER_SECOND = 2.3   # MMS's pace (PACE 0.92), measured: 9 words in 3.8 s
GAP = 0.3                # seconds kept between one line's end and the next's start
TRIES = 2

SYSTEM = "You write voice-overs for short premium product adverts: few words, well chosen, spoken slowly."

PROMPT = """Write the voice-over for this finished product advert. The film is planned; you add a calm voice
speaking over it.

Brief: {brief}

Brand: {brand} ({category}); its mood: {mood}. Avoid: {avoid}.

The film, {length:g} seconds in all (the end card included):
{shots}
Titles on screen: {titles}
End card: {card}

Write {lines} lines. Each is short (3 to 10 words) and starts at a time in seconds: let the film breathe, with
silence between lines and before the first (start it after 0.5 s). A line is spoken at about
{pace:g} words a second, so a line of n words lasts n / {pace:g} seconds: it must end before the next starts,
and the last before the ad ends. The last line, over the hero or the end card, says the brand's name.
Say what the pictures can't: a feeling, a moment, why it matters; don't describe the shots or repeat the
titles word for word. Plain words a voice can say: numbers written as words, no symbols, no claims a brand
couldn't stand behind (health, "the best").
The voice reads letters as plain English: also give the brand's name spelt the way it is said (brand_sounds),
so it's pronounced right."""


class Line(BaseModel):
    text: str = Field(min_length=1, max_length=120, description="what the voice says")
    start: float = Field(ge=0, description="seconds from the ad's start")


class VoiceOver(BaseModel):
    lines: list[Line] = Field(min_length=1, max_length=4)
    brand_sounds: str = Field("", max_length=60, description="the brand's name spelt as it is said, for a voice "
                                                             "that reads letters plainly (Lumen: Loomen; Noir: "
                                                             "Nwahr); empty if it reads as written")


def lines_wanted(length: float) -> str:
    return "two" if length <= 15 else "two or three" if length <= 30 else "three or four"


def spoken_seconds(text: str) -> float:
    """About how long the voice takes over `text`: its words at WORDS_PER_SECOND, and a pause per phrase break."""
    words = len(re.findall(r"[A-Za-z']+", text))
    return words / WORDS_PER_SECOND + speech.PAUSE * max(len(speech.phrases(text)) - 1, 0)


def said(text: str, brand: str, sounds: str) -> str:
    """The line as the voice should read it: the brand's name in its spoken spelling."""
    if not brand or not sounds.strip():
        return text
    return re.sub(rf"\b{re.escape(brand)}\b", sounds.strip(), text, flags=re.IGNORECASE)


def problems(vo: VoiceOver, sb: Storyboard, brand: str) -> list[str]:
    """What breaks the voice-over's rules: each a sentence for Spark."""
    out = []
    lines = sorted(vo.lines, key=lambda line: line.start)
    for i, line in enumerate(lines):
        ends = line.start + spoken_seconds(line.text)
        until = lines[i + 1].start - GAP if i + 1 < len(lines) else sb.length - GAP
        if line.start < 0.5:
            out.append(f"'{line.text}' starts at {line.start:g} s: start the first line after 0.5 s")
        if ends > until:
            out.append(f"'{line.text}' lasts about {spoken_seconds(line.text):.1f} s from {line.start:g} s, so it "
                       f"runs to {ends:.1f} s, past {until:.1f} s ("
                       + ("the next line's start" if i + 1 < len(lines) else "the ad's end")
                       + "): shorten it or start it earlier")
        if re.search(r"\d", line.text):
            out.append(f"'{line.text}' has digits: write numbers as words")
        if len(line.text.split()) > 12:
            out.append(f"'{line.text}' is long: keep a line to 10 words or fewer")
    if brand and lines and brand.casefold() not in lines[-1].text.casefold():
        out.append(f"the last line ('{lines[-1].text}') must say the brand's name, {brand}")
    spoken = sum(spoken_seconds(line.text) for line in lines)
    if spoken > 0.6 * sb.length:
        out.append(f"the lines take {spoken:.1f} s of the ad's {sb.length:g} s: leave more silence (at most "
                   f"{0.6 * sb.length:.1f} s spoken)")
    return out


def write(sb: Storyboard, brief: str, profile: BrandProfile | None, run: Run | None = None) -> VoiceOver | None:
    """The voice-over for `sb`, or None if Spark's still breaks the rules after TRIES."""
    brand = (profile.brand if profile else "") or (sb.end_card.name if sb.end_card else "")
    t, shots = 0.0, []
    for shot in sb.shots:
        shots.append(f"- {t:g}-{t + shot.duration:g} s: {shot.intent}")
        t += shot.duration
    card = f"{t:g}-{sb.length:g} s: {sb.end_card.name}" + (f", '{sb.end_card.tagline}'" if sb.end_card.tagline
                                                            else "") if sb.end_card else "none"
    prompt = PROMPT.format(brief=brief, brand=brand or "(none: name none)", category=profile.category if profile
                           else "product", mood=", ".join(profile.mood) if profile else "-",
                           avoid="; ".join(profile.do_not) if profile and profile.do_not else "-",
                           length=sb.length, shots="\n".join(shots),
                           titles="; ".join(f"'{x.text}' at {x.start:g} s" for x in sb.titles) or "none",
                           card=card, lines=lines_wanted(sb.length), pace=WORDS_PER_SECOND)
    found: list[str] = []
    for attempt in range(TRIES):
        ask = prompt if not found else prompt + "\n\nYour last voice-over broke these rules; fix them:\n" + \
            "\n".join(f"- {p}" for p in found)
        vo = VoiceOver.model_validate(spark.ask(ask, schema=VoiceOver, system=SYSTEM).data)
        found = problems(vo, sb, brand)
        if run:
            run.event("voiceover_draft", attempt=attempt, lines=[line.model_dump() for line in vo.lines],
                      problems=found)
        if not found:
            return vo
    return None


def voiceover(run: Run, sb: Storyboard, brief: str, profile: BrandProfile | None) -> Path | None:
    """The voice-over written, spoken and laid on a track as long as the ad
    (final/voice.wav), its lines saved (voiceover.json); None, with the
    reason logged, if it couldn't be: the ad is then made without one."""
    try:
        vo = write(sb, brief, profile, run)
        if vo is None:
            run.event("voiceover_failed", error=f"the lines still broke the rules after {TRIES} tries")
            return None
        brand = (profile.brand if profile else "") or (sb.end_card.name if sb.end_card else "")
        lines = sorted(vo.lines, key=lambda line: line.start)
        spoken = [(line.start, speech.speak(said(line.text, brand, vo.brand_sounds))) for line in lines]
        path = speech.track(spoken, sb.length, run.path("final", "voice.wav"))
    except Exception as e:   # noqa: BLE001 -- a voice-over is optional: the ad goes on without it
        run.event("voiceover_failed", error=f"{type(e).__name__}: {e}")
        return None
    run.save_json("voiceover.json", vo)
    run.event("voiceover", brand_sounds=vo.brand_sounds, lines=[{"text": line.text, "start": line.start,
                                   "seconds": round(speech.seconds(audio), 2)} for line, (_, audio) in
                                  zip(lines, spoken)])
    return path
