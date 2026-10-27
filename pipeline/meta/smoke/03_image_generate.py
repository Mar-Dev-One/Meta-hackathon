"""Muse Image, text to image: a product photo of a fictional brand, upright and
front-on like a photo a user would upload. 04, 05 and 07 reuse it."""

import base64

from _common import IMAGE, PRODUCT_PHOTO, meta_client, report, save_json, timed

PROMPT = (
    "Studio product photograph of a perfume bottle for a fictional brand: a rounded amber glass bottle "
    "with a polished gold cap and a cream paper label printed with the word NOCTIS in thin serif capitals. "
    "Straight-on front view, bottle upright and centered, whole bottle in frame with margin around it, "
    "seamless light grey background, soft even lighting, sharp focus."
)


def run() -> dict:
    client = meta_client()
    with timed() as t:
        result = client.images.generate(
            model=IMAGE,
            prompt=PROMPT,
            size="1024x1536",
            extra_body={"output_format": "png"},   # the default is webp
        )
    PRODUCT_PHOTO.write_bytes(base64.b64decode(result.data[0].b64_json))
    meta = result.model_dump()
    for item in meta.get("data", []):
        item.pop("b64_json", None)
    save_json("03_image_generate.json", meta)

    from PIL import Image
    with Image.open(PRODUCT_PHOTO) as image:
        size = image.size
    return {"latency_s": t.seconds, "saved": str(PRODUCT_PHOTO), "size": f"{size[0]}x{size[1]} (asked 1024x1536)"}


if __name__ == "__main__":
    report(run())
