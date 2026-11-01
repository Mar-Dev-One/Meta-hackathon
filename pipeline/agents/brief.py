"""A spoken brief: a recording to the brief's text. Muse Voice transcribes
it; Muse Spark then mends what the ear got wrong in a product ad's words
("and on the battle" in a perfume brief is "end on the bottle"), and only
that: it doesn't rewrite the brief.

    text, heard = spoken_brief("brief.webm")   # any format ffmpeg reads
    python -m pipeline.agents.brief brief.m4a
"""

from pathlib import Path

from pydantic import BaseModel, Field

from pipeline.meta import spark, voice

SYSTEM = "You correct speech-recognition mistakes in briefs for product adverts."

PROMPT = """A brief for a short product advert, spoken and transcribed by speech recognition:

{heard}

Correct only words the recognition got wrong: words that sound alike but make no sense in an ad brief
(a perfume "battle" is a "bottle"), words it heard twice ("and on and on the bottle" for "end on the
bottle"), numbers written as words ("fifteen seconds" is "15 seconds"), missing punctuation. Keep
everything else as it was said: the same words, order and meaning; add nothing, drop nothing else,
don't polish the style."""


class Brief(BaseModel):
    brief: str = Field(description="the transcript with the recognition's mistakes corrected, nothing else changed")


def spoken_brief(audio: Path | str) -> tuple[str, str]:
    """(the brief, what was heard): the recording transcribed, its
    mishearings mended. If the mending fails, the transcript as heard."""
    heard = voice.transcribe(audio).strip()
    if not heard:
        return "", ""
    try:
        answer = spark.ask(PROMPT.format(heard=heard), schema=Brief, system=SYSTEM)
        return Brief.model_validate(answer.data).brief.strip() or heard, heard
    except Exception:   # noqa: BLE001 -- the transcript as heard is still a brief
        return heard, heard


if __name__ == "__main__":
    import sys

    text, heard = spoken_brief(sys.argv[1])
    print(f"heard: {heard}\nbrief: {text}")
