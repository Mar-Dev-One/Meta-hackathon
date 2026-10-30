"""Muse Spark: text, vision, JSON answers and tool calling.

    from pipeline.meta import spark
    r = spark.ask("Describe this bottle's materials.", images=[photo], schema=Materials)
    r.data          # a Materials (validated), r.text the raw answer

    r = spark.run_tools(brief, tools=TOOLS, handle=lambda name, args: studio_call(name, args))
    r.calls         # every tool call made, with its result

A tool can show the model pictures (a render it made): handle() returns
Seen(result, images), and the images follow that turn's results.

`provider="baseten"` runs the same request on Muse Spark Open (Chat
Completions on Baseten); tool calling is Meta API only for now.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from . import cache, client, config, usage
from .client import ImageInput, MetaError


@dataclass
class Seen:
    """A tool's result with images for the model to look at (run_tools)."""
    result: Any
    images: list[ImageInput]


@dataclass
class SparkResult:
    text: str                         # the final answer as written
    data: Any = None                  # with a schema: the parsed (and, for a pydantic model, validated) answer
    calls: list[dict] = field(default_factory=list)   # run_tools(): {"name", "arguments", "result"} in order
    model: str = ""
    cached: bool = False


def _schema_of(schema: type[BaseModel] | dict) -> tuple[str, dict]:
    if isinstance(schema, dict):
        return schema.get("title", "answer"), schema
    return schema.__name__, schema.model_json_schema()


def _parse(model: str, text: str, schema: type[BaseModel] | dict | None) -> Any:
    if schema is None:
        return None
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise MetaError(model, f"the answer isn't JSON ({e}): {text[:300]}")
    if isinstance(schema, dict):
        return data
    try:
        return schema.model_validate(data)
    except ValidationError as e:
        raise MetaError(model, f"the answer doesn't match {schema.__name__}: {e}")


def _user_content(prompt: str, images: list[ImageInput], chat: bool) -> list[dict]:
    """The user message's parts: the images, then the text."""
    parts = []
    for image in images:
        url = client.data_url(*client.image_bytes(image))
        parts.append({"type": "image_url", "image_url": {"url": url}} if chat else {"type": "input_image", "image_url": url})
    parts.append({"type": "text", "text": prompt} if chat else {"type": "input_text", "text": prompt})
    return parts


def _usage_numbers(u) -> tuple[int, int, int]:
    """(input, cached input, output) tokens from a Responses or Chat usage object."""
    if u is None:
        return 0, 0, 0
    inputs = getattr(u, "input_tokens", None) or getattr(u, "prompt_tokens", 0) or 0
    outputs = getattr(u, "output_tokens", None) or getattr(u, "completion_tokens", 0) or 0
    details = getattr(u, "input_tokens_details", None) or getattr(u, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0 if details else 0
    return inputs, cached, outputs


def _record(kind: str, model: str, began: float, cached: bool, numbers=(0, 0, 0)) -> None:
    i, c, o = numbers
    usage.record(usage.Call(kind=kind, model=model, cached=cached, seconds=round(time.perf_counter() - began, 3),
                            input_tokens=i, cached_input_tokens=c, output_tokens=o,
                            cost=0.0 if cached else usage.token_cost(model, i, c, o)))


def ask(prompt: str, *, images: list[ImageInput] = (), schema: type[BaseModel] | dict | None = None,
        system: str | None = None, model: str | None = None, provider: str = "meta",
        reasoning: str | None = None, cache_ok: bool = True, sample: int = 0) -> SparkResult:
    """One question, optionally with images and an answer schema. `sample`
    asks the same again as a new sample (its own cache entry; the model sees
    the same request): for measuring how much answers vary."""
    images = list(images)
    chat = provider == "baseten"
    model = model or (config.SPARK_OPEN if chat else config.SPARK)
    schema_name, schema_json = _schema_of(schema) if schema is not None else (None, None)

    request = {"model": model, "provider": provider, "prompt": prompt, "system": system,
               "images": client.image_keys(images), "schema": schema_json, "reasoning": reasoning}
    if sample:
        request["sample"] = sample   # only when set, so sample 0 keeps the keys cached before it existed
    key = cache.request_key("spark.ask", request)
    began = time.perf_counter()
    stored = cache.get_json(key, cache_ok)
    if stored is not None:
        _record("text", model, began, True)
        return SparkResult(text=stored["text"], data=_parse(model, stored["text"], schema), model=model, cached=True)

    def request() -> tuple[str, tuple[int, int, int]]:
        if chat:
            messages = ([{"role": "system", "content": system}] if system else []) + \
                       [{"role": "user", "content": _user_content(prompt, images, chat=True)}]
            extra = {"response_format": {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema_json}}} \
                if schema_json else {}
            response = client.baseten().chat.completions.create(model=model, messages=messages, **extra)
            return response.choices[0].message.content or "", _usage_numbers(response.usage)
        extra = {}
        if system:
            extra["instructions"] = system
        if schema_json:
            extra["text"] = {"format": {"type": "json_schema", "name": schema_name, "schema": schema_json}}
        if reasoning:
            extra["reasoning"] = {"effort": reasoning}
        response = client.meta().responses.create(
            model=model, input=[{"type": "message", "role": "user", "content": _user_content(prompt, images, chat=False)}],
            **extra)
        return response.output_text, _usage_numbers(response.usage)

    text, numbers = client.call(model, request)
    _record("text", model, began, False, numbers)
    data = _parse(model, text, schema)    # parse before caching: a bad answer isn't kept
    cache.put_json(key, {"text": text})
    return SparkResult(text=text, data=data, model=model)


def run_tools(prompt: str, *, tools: list[dict], handle: Callable[[str, dict], Any], images: list[ImageInput] = (),
              system: str | None = None, model: str | None = None, max_turns: int = 8,
              cache_ok: bool = True) -> SparkResult:
    """Lets Muse Spark call `tools` (Responses-format function definitions)
    until it answers without calling any, or `max_turns` runs out. Each call
    goes to handle(name, arguments); its return value (JSON-able) goes back
    to the model. Every turn is cached by the conversation so far, so a rerun
    replays the same calls without paying for them -- but handle() still runs,
    so its side effects (building a scene) happen again."""
    model = model or config.SPARK
    history: list[dict] = [{"type": "message", "role": "user", "content": _user_content(prompt, list(images), chat=False)}]
    calls: list[dict] = []
    all_cached = True

    for turn in range(max_turns):
        key = cache.request_key("spark.tools", {"model": model, "system": system, "tools": tools,
                                                "images": client.image_keys(list(images)),
                                                "history": history[1:], "prompt": prompt})
        began = time.perf_counter()
        stored = cache.get_json(key, cache_ok)
        if stored is None:
            all_cached = False
            extra = {"instructions": system} if system else {}
            response = client.call(model, lambda: client.meta().responses.create(model=model, input=history,
                                                                                 tools=tools, **extra))
            # The whole output (reasoning included) goes back with the next
            # turn, as the model produced it.
            stored = {"text": response.output_text,
                      "output": [i.model_dump(exclude_none=True) for i in response.output]}
            _record("tools", model, began, False, _usage_numbers(response.usage))
            cache.put_json(key, stored)
        else:
            _record("tools", model, began, True)

        turn_calls = [i for i in stored["output"] if i.get("type") == "function_call"]
        if not turn_calls:
            return SparkResult(text=stored["text"], calls=calls, model=model, cached=all_cached)

        # Answer every call of this turn, then send the whole exchange back.
        history.extend({k: v for k, v in item.items() if k != "status"} for item in stored["output"])
        seen: list[tuple[str, list[ImageInput]]] = []
        for call in turn_calls:
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments, result = {}, {"error": "arguments weren't valid JSON"}
            else:
                try:
                    result = handle(call["name"], arguments)
                except Exception as e:   # noqa: BLE001 -- the model sees the error and can correct itself
                    result = {"error": str(e)}
            if isinstance(result, Seen):
                seen.append((call["name"], result.images))
                result = result.result
            calls.append({"turn": turn, "name": call["name"], "arguments": arguments, "result": result})
            history.append({"type": "function_call_output", "call_id": call["call_id"],
                            "output": json.dumps(result, default=str)})
        # Function outputs are text only: the pictures come as the user's next message.
        for name, images in seen:
            history.append({"type": "message", "role": "user", "content": _user_content(
                f"The images from your {name} call, in the order of its results.", images, chat=False)})

    raise MetaError(model, f"still calling tools after {max_turns} turns ({len(calls)} calls)")
