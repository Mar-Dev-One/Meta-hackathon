"""Muse Image: a product photo of a fictional brand, upright and front-on
like a photo a user would upload. 04, 05 and 07 reuse it."""

from PIL import Image

from _common import PRODUCT_PHOTO, report

from pipeline.meta import image, usage

PROMPT = (
    "Studio product photograph of a perfume bottle for a fictional brand: a rounded amber glass bottle "
    "with a polished gold cap and a cream paper label printed with the word NOCTIS in thin serif capitals. "
    "Straight-on front view, bottle upright and centered, whole bottle in frame with margin around it, "
    "seamless light grey background, soft even lighting, sharp focus."
)


def run() -> dict:
    path = image.generate(PROMPT, size="1024x1536", out=PRODUCT_PHOTO)
    with Image.open(path) as im:
        size = im.size
    last = usage.calls()[-1]
    return {"cached": last.cached, "seconds": last.seconds, "saved": str(path),
            "size": f"{size[0]}x{size[1]} (asked 1024x1536)"}


if __name__ == "__main__":
    report(run())
