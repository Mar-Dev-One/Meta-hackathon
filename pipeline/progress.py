"""How far along a run is: its steps, each with an estimate of how long it
takes, and a "progress" event in the run's log every TICK seconds (the
step, the share of the whole run done, the seconds left), from a thread of
its own, so it keeps coming while a render or a model call blocks.

    progress = Progress(run, [("analyse", "Reading the photo", 15), ("render", "Rendering", 300)])
    progress.start("analyse")
    progress.start("render", seconds=render_seconds(450, 1920, 1080, "live"))
    progress.close()                        # all done (or the run failed: the ticks stop)

A step can be skipped (it turned out not to be needed) or re-estimated once
more is known. Estimates are just that: a step running long holds at 95% of
its share until it ends. Renders' speeds are learned from the last ones on
this machine (cache/render_speed.json), per director: their scenes differ.
"""

import json
import threading
import time
from pathlib import Path

from pipeline.runs import Run

TICK = 5.0                                   # seconds between progress events
SPEEDS = Path("cache/render_speed.json")    # seconds a 1080p frame (16 samples) takes, per director
SPEED = {"storyboard": 0.5, "live": 1.0}    # until one has been measured
LEARN = 0.5                                  # how much a new measurement moves the stored speed
OUTLIER = 3.0                                # a measurement this many times slower than the stored one is ignored


def _speeds() -> dict:
    try:
        return SPEED | json.loads(SPEEDS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(SPEED)


def render_seconds(frames: int, width: int, height: int, director: str) -> float:
    """About how long a render of `frames` frames at width x height takes."""
    return 15 + frames * _speeds().get(director, 1.0) * (width * height) / (1920 * 1080)


def learn(seconds: float, frames: int, width: int, height: int, director: str) -> None:
    """Remembers how fast a render went, for the next estimates."""
    if frames <= 0 or seconds <= 0:
        return
    speeds = _speeds()
    measured = seconds / frames * (1920 * 1080) / (width * height)
    if measured > OUTLIER * speeds.get(director, measured):
        return   # not a render's speed: the machine slept, or the network dropped, while it ran
    speeds[director] = round((1 - LEARN) * speeds.get(director, measured) + LEARN * measured, 4)
    SPEEDS.parent.mkdir(parents=True, exist_ok=True)
    SPEEDS.write_text(json.dumps(speeds, indent=2), encoding="utf-8")


class Progress:
    def __init__(self, run: Run, steps: list[tuple[str, str, float]]):
        self.run = run
        self.steps = {key: {"label": label, "seconds": float(seconds), "state": "todo"} for key, label, seconds in steps}
        self.current: str | None = None
        self.began = time.monotonic()
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        threading.Thread(target=self._tick, name="progress", daemon=True).start()

    def start(self, key: str, seconds: float | None = None, label: str | None = None) -> None:
        """`key` is now under way (every step before it in the plan is done,
        or skipped if it never started)."""
        with self.lock:
            for k, step in self.steps.items():
                if k == key:
                    break
                if step["state"] == "running":
                    step["state"] = "done"
                elif step["state"] == "todo":
                    step["state"] = "skipped"
            step = self.steps[key]
            step.update(state="running", began=time.monotonic())
            if seconds is not None:
                step["seconds"] = float(seconds)
            if label:
                step["label"] = label
            self.current = key
        self._emit()

    def estimate(self, key: str, seconds: float) -> None:
        with self.lock:
            self.steps[key]["seconds"] = float(seconds)

    def skip(self, key: str) -> None:
        """`key` turned out not to be needed (even if it had started)."""
        with self.lock:
            if self.steps[key]["state"] in ("todo", "running"):
                self.steps[key]["state"] = "skipped"
                if self.current == key:
                    self.current = None

    def close(self, done: bool = True) -> None:
        """Stops the ticks; with `done`, a last event at 100%."""
        self.stopped.set()
        if done:
            with self.lock:
                for step in self.steps.values():
                    if step["state"] == "running":
                        step["state"] = "done"
                self.current = None
            self._emit()

    def snapshot(self) -> dict:
        with self.lock:
            counted = [s for s in self.steps.values() if s["state"] != "skipped"]
            total = sum(s["seconds"] for s in counted) or 1.0
            done = sum(s["seconds"] for s in counted if s["state"] == "done")
            left = sum(s["seconds"] for s in counted if s["state"] == "todo")
            step = self.steps.get(self.current) if self.current else None
            if step:
                ran = time.monotonic() - step["began"]
                done += min(ran, 0.95 * step["seconds"])
                left += max(step["seconds"] - ran, 0.05 * step["seconds"])
            names = [s["label"] for s in counted]
            return {"step": step["label"] if step else "Done", "fraction": round(min(done / total, 1.0), 3),
                    "left": round(left) if step else 0, "elapsed": round(time.monotonic() - self.began),
                    "number": names.index(step["label"]) + 1 if step else len(names), "steps": len(names)}

    def _emit(self) -> None:
        self.run.event("progress", **self.snapshot())

    def _tick(self) -> None:
        while not self.stopped.wait(TICK):
            self._emit()
