"""Muse Spark tool calling over the Responses API, with tools shaped like the
Studio's commands: does it call them with sensible arguments, several in one
turn, and continue after getting the results back? This decides how the
director drives the Studio."""

import json

from _common import SPARK, meta_client, report, save_json, timed

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
                "fov_degrees": {"type": "number", "description": "vertical field of view, 1 to 170"},
            },
            "required": ["position", "target"],
        },
    },
    {
        "type": "function",
        "name": "light_add",
        "description": "Adds a light. Spot lights aim at the target.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["point", "spot", "directional"]},
                "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "target": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
                "color_temperature_k": {"type": "number"},
                "intensity": {"type": "number"},
            },
            "required": ["type", "position", "intensity"],
        },
    },
]

BRIEF = (
    "Set up the opening shot of a dark, moody perfume ad. The bottle is 12 cm tall at the origin. "
    "Place the camera low and close, slightly below the cap, looking at the bottle, and add a warm rim light "
    "behind it plus a faint cool fill from the front. Use the tools, then describe the shot in one sentence."
)


def run() -> dict:
    client = meta_client()
    calls = []
    turns = 0
    with timed() as t:
        response = client.responses.create(model=SPARK, input=BRIEF, tools=TOOLS)
        while turns < 4:
            turns += 1
            pending = [item for item in response.output if item.type == "function_call"]
            if not pending:
                break
            outputs = []
            for item in pending:
                args = json.loads(item.arguments)
                calls.append({"turn": turns, "name": item.name, "arguments": args})
                outputs.append({"type": "function_call_output", "call_id": item.call_id,
                                "output": json.dumps({"ok": True})})
            response = client.responses.create(model=SPARK, previous_response_id=response.id,
                                               input=outputs, tools=TOOLS)
    save_json("02_spark_tools.json", {"calls": calls, "final": response.model_dump()})
    per_turn = [sum(1 for c in calls if c["turn"] == n) for n in range(1, turns + 1)]
    return {
        "latency_s": t.seconds,
        "tool_calls": len(calls),
        "calls_per_turn": per_turn,
        "calls": "; ".join(f"{c['name']}({json.dumps(c['arguments'])})" for c in calls),
        "final_text": response.output_text,
    }


if __name__ == "__main__":
    report(run())
