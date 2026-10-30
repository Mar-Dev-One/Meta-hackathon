"""A client for the Studio's command server (README.md, "Command server").

    async with Studio() as studio:            # starts build/Release/Studio.exe --hidden
        await studio.call("studio.reset")
        await studio.call("camera.move", move="orbit", subject="product", duration=4)

Every command's result comes back as a dict; a failed command raises
StudioError with the server's code and message (which say what to fix).
"""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXE = ROOT / "build" / "Release" / "Studio.exe"


class StudioError(Exception):
    def __init__(self, method: str, code: str, message: str):
        super().__init__(f"{method}: {message} ({code})")
        self.method, self.code, self.message = method, code, message


class StudioTimeout(TimeoutError):
    """The Studio didn't answer a command in time (hung); it was stopped."""


class Studio:
    """Starts a Studio (or attaches to a running one) and runs commands on it."""

    def __init__(self, exe: Path | str | None = None, hidden: bool | None = None, width: int = 1280, height: int = 720,
                 port: int = 0, attach: bool = False):
        self.exe = Path(exe or os.environ.get("STUDIO_EXE", DEFAULT_EXE))
        if hidden is None:   # STUDIO_VISIBLE=1: its window shown and its log printed (start.bat)
            hidden = os.environ.get("STUDIO_VISIBLE") != "1"
        self.hidden, self.width, self.height, self.port, self.attach = hidden, width, height, port, attach
        self.process: subprocess.Popen | None = None
        self.ws = None
        self._next_id = 0
        # functions(method, params, seconds, error or None), told of every
        # command once it's answered (a run logs them: pipeline.runs).
        self.listeners: list = []

    @property
    def server_json(self) -> Path:
        return self.exe.parent / "server.json"

    async def start(self, timeout: float = 30.0) -> "Studio":
        if not self.attach:
            if not self.exe.exists():
                raise FileNotFoundError(f"no Studio at {self.exe}: build it (README.md) or set STUDIO_EXE")
            self.server_json.unlink(missing_ok=True)   # so the one we wait for is this run's
            args = [str(self.exe), "--width", str(self.width), "--height", str(self.height)]
            if self.hidden:
                args.append("--hidden")
            if self.port:
                args += ["--port", str(self.port)]
            self.process = subprocess.Popen(args, cwd=self.exe.parent,
                                            stdout=subprocess.DEVNULL if self.hidden else None)

        info = await self._wait_for_server(timeout)
        # Renders block the Studio, which then can't answer pings: no ping timeout.
        self.ws = await websockets.connect(info["url"], max_size=None, ping_interval=None)
        return self

    async def _wait_for_server(self, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                raise RuntimeError(f"the Studio exited (code {self.process.returncode}) before its server started")
            try:
                info = json.loads(self.server_json.read_text())
                if not self.process or info.get("pid") == self.process.pid:
                    return info
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            await asyncio.sleep(0.1)
        raise TimeoutError(f"no {self.server_json} after {timeout:.0f}s")

    async def call(self, method: str, _timeout: float | None = None, **params) -> dict:
        """Runs one command; its result, or StudioError. With `_timeout`
        (seconds), a Studio that hasn't answered by then is taken to have
        hung: it's stopped and StudioTimeout raised (restart() starts a new one)."""
        self._next_id += 1
        request_id = self._next_id
        began = time.monotonic()
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}))

        async def answer() -> dict:
            while True:
                reply = json.loads(await self.ws.recv())
                if reply.get("id") == request_id:
                    return reply   # anything else is a notification (scene.changed), not our reply

        try:
            reply = await asyncio.wait_for(answer(), _timeout)
        except asyncio.TimeoutError:
            await self.close()
            raise StudioTimeout(f"{method}: no answer after {_timeout:.0f} s; the Studio was stopped") from None
        error = None
        if "error" in reply:
            e = reply["error"]
            error = StudioError(method, (e.get("data") or {}).get("code", str(e.get("code"))), e.get("message", ""))
        for listener in self.listeners:
            listener(method, params, round(time.monotonic() - began, 3), error)
        if error:
            raise error
        return reply.get("result") or {}

    async def restart(self) -> "Studio":
        """A new Studio in place of this one (after a StudioTimeout): an empty stage."""
        await self.close()
        return await self.start()

    async def close(self) -> None:
        if self.ws:
            try:
                await asyncio.wait_for(self.ws.close(), 5)   # a hung Studio never answers the close
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                pass
            self.ws = None
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    async def __aenter__(self) -> "Studio":
        return await self.start()

    async def __aexit__(self, *exc) -> None:
        await self.close()
