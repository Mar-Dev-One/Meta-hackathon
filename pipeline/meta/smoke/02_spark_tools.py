"""Muse Spark tool calling, with tools shaped like the Studio's commands:
sensible arguments, several calls per turn, and carrying on after results."""

import json

from _common import report

from pipeline.meta import spark

TOOLS = [
    {
        "type": "function",
        "name": "camera_set",
        "description": "Creates or moves the camera and aims it at a point. Meters; +Y is up; the product stands at the origin.",
        "parameters": {
            "type": "object",
            "properties": {
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "target": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "fov_degrees": {"type": "number", "description": "vertical field of view, 1 to 179"},
            },
            "required": ["position", "target"],
        },
    },
    {
        "type": "function",
        "name": "light_add",
        "description": "Adds a spot light aimed at the target. Intensity: 1 is a soft fill, 10 a strong key, 30 a hard rim.",
        "parameters": {
            "type": "object",
            "properties": {
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "target": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "color_temperature_k": {"type": "number"},
                "intensity": {"type": "number"},
            },
            "required": ["position", "intensity"],
        },
    },
]

BRIEF = (
    "Set up the opening shot of a dark, moody perfume ad. The bottle is 12 cm tall at the origin. "
    "Place the camera low and close, slightly below the cap, looking at the bottle, and add a warm rim light "
    "behind it plus a faint cool fill from the front. Use the tools, then describe the shot in one sentence."
)


def run() -> dict:
    r = spark.run_tools(BRIEF, tools=TOOLS, handle=lambda name, args: {"ok": True})
    turns = sorted({c["turn"] for c in r.calls})
    return {"cached": r.cached, "tool_calls": len(r.calls),
            "calls_per_turn": [sum(1 for c in r.calls if c["turn"] == t) for t in turns],
            "calls": "; ".join(f"{c['name']}({json.dumps(c['arguments'])})" for c in r.calls),
            "final_text": r.text}


if __name__ == "__main__":
    report(run())
