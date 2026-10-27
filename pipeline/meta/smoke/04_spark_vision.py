"""Muse Spark vision: can it read a product photo into the facts the brand
analyst needs (parts, colours, materials, label text, mood) as JSON?"""

import json

from _common import SPARK, data_url, meta_client, product_photo, report, save_json, timed

QUESTION = (
    "This is a product photo. Reply with JSON only, no prose, in this shape: "
    '{"category": str, "brand_text": str, "parts": [{"name": str, "color_hex": str, '
    '"metallic": number 0-1, "roughness": number 0-1, "transparent": bool}], '
    '"palette_hex": [str], "typography": str, "mood": [str]}'
)


def run() -> dict:
    client = meta_client()
    with timed() as t:
        response = client.responses.create(
            model=SPARK,
            input=[{
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": QUESTION},
                    {"type": "input_image", "image_url": data_url(product_photo())},
                ],
            }],
        )
    save_json("04_spark_vision.json", response.model_dump())

    text = response.output_text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
        valid = "yes"
    except json.JSONDecodeError as e:
        parsed, valid = text, f"no ({e})"
    return {"latency_s": t.seconds, "valid_json": valid, "answer": json.dumps(parsed) if valid == "yes" else parsed}


if __name__ == "__main__":
    report(run())
