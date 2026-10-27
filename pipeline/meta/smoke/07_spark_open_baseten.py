"""Muse Spark Open on Baseten (Chat Completions): text, then vision on the
product photo if there is one. The candidate for the critic, and for the
open-weight prize."""

from _common import SPARK_OPEN, PRODUCT_PHOTO, baseten_client, data_url, report, save_json, timed


def run() -> dict:
    client = baseten_client()
    result = {}

    with timed() as t:
        text = client.chat.completions.create(
            model=SPARK_OPEN,
            messages=[{"role": "user", "content": "In one sentence: what is a rim light in product photography?"}],
        )
    result["text_latency_s"] = t.seconds
    result["text_answer"] = text.choices[0].message.content

    if PRODUCT_PHOTO.exists():
        with timed() as t:
            vision = client.chat.completions.create(
                model=SPARK_OPEN,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": "Score this product photo's lighting from 0 to 10 and give one specific fix."},
                    {"type": "image_url", "image_url": {"url": data_url(PRODUCT_PHOTO)}},
                ]}],
            )
        result["vision_latency_s"] = t.seconds
        result["vision_answer"] = vision.choices[0].message.content
        save_json("07_spark_open_baseten.json", {"text": text.model_dump(), "vision": vision.model_dump()})
    else:
        result["vision"] = "skipped: run 03_image_generate.py first"
        save_json("07_spark_open_baseten.json", {"text": text.model_dump()})
    return result


if __name__ == "__main__":
    report(run())
