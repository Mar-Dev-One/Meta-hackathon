"""Muse Spark Open on Baseten: text, then vision on the product photo. The
candidate for the critic, and for the open-weight prize."""

from _common import PRODUCT_PHOTO, report

from pipeline.meta import spark


def run() -> dict:
    text = spark.ask("In one sentence: what is a rim light in product photography?", provider="baseten")
    result = {"text_answer": text.text}
    if PRODUCT_PHOTO.exists():
        vision = spark.ask("Score this product photo's lighting from 0 to 10 and give one specific fix.",
                           images=[PRODUCT_PHOTO], provider="baseten")
        result["vision_answer"] = vision.text
    return result


if __name__ == "__main__":
    report(run())
