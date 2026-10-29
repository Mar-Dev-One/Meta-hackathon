"""Writes each schema's JSON Schema to pipeline/schemas/json/, for prompts
and for reading. (spark.ask() takes the pydantic models directly.)

    python -m pipeline.schemas.export
"""

import json
from pathlib import Path

from pipeline.schemas import AdCritique, BrandProfile, Critique, Storyboard

OUT = Path(__file__).resolve().parent / "json"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for model in (Storyboard, BrandProfile, Critique, AdCritique):
        path = OUT / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(by_alias=True), indent=2), encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
