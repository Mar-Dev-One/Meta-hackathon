"""Every Studio command as a tool Muse Spark can call: the definitions come
from the Studio itself (commands.list), so a command added to the Studio is
a tool the next time, with nothing to write here.

    bridge = await Bridge.open(studio)                 # the tools, read from the Studio
    r = await bridge.run(prompt, system=..., max_turns=40)   # Spark builds with them
    r.calls                                            # every command it ran, with its result

A tool's name is its command's with "." as "__" (function names can't have
dots): entity__place runs entity.place. shot.preview's frames are shown to
Spark as images, so it sees what it builds (each preview in its own numbered
folder under `previews`, if given, so none overwrites another). `extra`
tools sit beside the commands: {name: (definition, async handler(args))};
`refuse(command, args)` can turn a command down before it runs, with the
reason as its error. Spark runs in a worker thread
and each command on the Studio's event loop: run_tools waits for the model,
the Studio for the GPU, and neither blocks the other's loop.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable

from pipeline.meta import spark

from .client import Studio, StudioError, StudioTimeout

# The Studio's argument types as JSON schema.
TYPES = {
    "number": {"type": "number"},
    "string": {"type": "string"},
    "boolean": {"type": "boolean"},
    "vec3": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
    "entity": {"type": "string", "description": "an entity's name (or id)"},
    "component": {"type": "string"},
    "object": {"type": "object", "additionalProperties": True},
    "array": {"type": "array", "items": {}},
}
LOOSE = {("timeline.add_key", "value")}   # a number or a list: no type at all
LIMIT = 600   # seconds a command may take before the Studio is taken to have hung (a long shot.render included)


def tool_name(command: str) -> str:
    return command.replace(".", "__")


def command_name(tool: str) -> str:
    return tool.replace("__", ".")


def definitions(commands: list[dict]) -> list[dict]:
    """Responses-format function definitions for `commands` (commands.list's)."""
    tools = []
    for c in commands:
        properties, required = {}, []
        for a in c.get("args", []):
            schema = {} if (c["name"], a["name"]) in LOOSE else dict(TYPES.get(a["type"], {}))
            schema["description"] = a.get("description", "")
            properties[a["name"]] = schema
            if a.get("required"):
                required.append(a["name"])
        tools.append({"type": "function", "name": tool_name(c["name"]), "description": c.get("description", ""),
                      "parameters": {"type": "object", "properties": properties, "required": required}})
    return tools


class Bridge:
    """The Studio's commands as Spark's tools, run on `studio`."""

    def __init__(self, studio: Studio, commands: list[dict], on_call: Callable[[str, dict, Any], None] | None = None,
                 extra: dict[str, tuple[dict, Callable]] | None = None, previews: Path | None = None,
                 refuse: Callable[[str, dict], str | None] | None = None):
        self.studio, self.commands, self.refuse = studio, commands, refuse
        self.extra = extra or {}
        self.tools = definitions(commands) + [definition for definition, _ in self.extra.values()]
        self.on_call = on_call   # told of every command run: (command, args, result or {"error"})
        self.previews, self.preview_count = previews, 0
        self.loop: asyncio.AbstractEventLoop | None = None

    @classmethod
    async def open(cls, studio: Studio, on_call=None, extra=None, previews: Path | None = None,
                   refuse=None) -> "Bridge":
        return cls(studio, (await studio.call("commands.list"))["commands"], on_call, extra, previews, refuse)

    def handle(self, tool: str, args: dict) -> Any:
        """Runs one tool call (from run_tools' thread) on the Studio's loop."""
        command = tool if tool in self.extra else command_name(tool)
        reason = self.refuse(command, args) if self.refuse else None
        if reason:
            if self.on_call:
                self.on_call(command, args, {"error": reason})
            return {"error": reason}
        if command == "shot.preview" and self.previews:
            self.preview_count += 1
            args = args | {"out_dir": str(self.previews / f"{self.preview_count:03d}")}
        call = self.extra[tool][1](args) if tool in self.extra else self.studio.call(command, _timeout=LIMIT, **args)
        try:
            result = asyncio.run_coroutine_threadsafe(call, self.loop).result()
        except StudioError as e:
            result = {"error": e.message, "code": e.code}
        except StudioTimeout as e:
            raise spark.Stop(str(e)) from e
        except Exception as e:   # noqa: BLE001 -- an extra tool's own failure: logged, and Spark told
            result = {"error": f"{type(e).__name__}: {e}"}
        if self.on_call:
            self.on_call(command, args, result)
        if command == "shot.preview" and "frames" in result:
            frames = [Path(f["path"]) for f in result["frames"]]
            return spark.Seen(result, [f for f in frames if f.exists()])
        return result

    async def run(self, prompt: str, *, system: str | None = None, images: list = (), max_turns: int = 40,
                  cache_ok: bool = True) -> spark.SparkResult:
        """Spark working with the Studio's commands until it answers without
        calling any (or `max_turns` runs out: MetaError)."""
        self.loop = asyncio.get_running_loop()
        return await asyncio.to_thread(spark.run_tools, prompt, tools=self.tools, handle=self.handle,
                                       images=list(images), system=system, max_turns=max_turns, cache_ok=cache_ok)
