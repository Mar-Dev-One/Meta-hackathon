"""Run folders: everything one job did, in one place, replayable.

    runs/20261028-031502-noctis/
      log.jsonl        every event, one JSON object per line: {"t": seconds since the start, "kind", ...}
      run.json         the summary, written at the end: status, length, cost, outputs
      inputs/          what it was given (brief, photos)
      storyboard.json  what was planned (and brand_profile.json, critiques/, ...)
      frames/          previews the critic looked at
      final/           the video

    with Run.create("noctis") as run:
        run.save_json("storyboard.json", storyboard)
        run.event("render", frames=390)
    # an exception records "failed" (with the error) and is raised again

Every Meta model call made while a run is open is logged into it with its
cost (pipeline.meta.usage). `python -m pipeline.runs` lists runs, shows one,
or replays it with its timing (for the demo).
"""

import json
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from pipeline.meta import usage

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"


class Run:
    def __init__(self, root: Path):
        self.root = root
        self.started = time.time()
        self.status = "running"
        self.outputs: dict[str, str] = {}
        self._usage_from = len(usage.calls())
        self._watched: list = []
        self._writing = threading.Lock()

    # --- Making and opening ---------------------------------------------------------

    @classmethod
    def create(cls, slug: str, base: Path = RUNS) -> "Run":
        """A new run folder: runs/<date>-<time>-<slug>."""
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug.lower()).strip("-") or "run"
        root = base / f"{datetime.now():%Y%m%d-%H%M%S}-{safe}"
        n = 2
        while root.exists():
            root = base / f"{datetime.now():%Y%m%d-%H%M%S}-{safe}-{n}"
            n += 1
        root.mkdir(parents=True)
        run = cls(root)
        run.event("started", slug=slug)
        return run

    @classmethod
    def reopen(cls, root: Path | str) -> "Run":
        """An existing run folder, to carry on where it stopped (a "resumed"
        event in its log). Its time, cost and outputs in run.json count from
        here on."""
        root = Path(root).resolve()   # absolute, like create()'s: the Studio writes into it from its own folder
        if not (root / "log.jsonl").exists():
            raise FileNotFoundError(f"{root} isn't a run folder (no log.jsonl)")
        run = cls(root)
        run.event("resumed")
        return run

    def __enter__(self) -> "Run":
        usage.add_listener(self._on_model_call)
        return self

    def watch(self, studio) -> None:
        """Logs every command `studio` (pipeline.studio.Studio) runs from now
        until the run ends, as "studio" events."""
        studio.listeners.append(self._on_studio_call)
        self._watched.append(studio)

    def __exit__(self, kind, error, trace) -> None:
        usage.remove_listener(self._on_model_call)
        for studio in self._watched:
            if self._on_studio_call in studio.listeners:
                studio.listeners.remove(self._on_studio_call)
        if error is not None:
            self.event("failed", error=f"{type(error).__name__}: {error}")
            self.finish("failed")
        elif self.status == "running":
            self.finish("done")

    # --- Writing --------------------------------------------------------------------

    def path(self, *parts: str) -> Path:
        """A path inside the run, its folder made."""
        p = self.root.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def folder(self, *parts: str) -> Path:
        """A folder inside the run, made."""
        p = self.root.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def event(self, kind: str, **data: Any) -> dict:
        """Appends one event to log.jsonl and returns it."""
        entry = {"t": round(time.time() - self.started, 3), "time": datetime.now().isoformat(timespec="milliseconds"),
                 "kind": kind, **data}
        line = json.dumps(entry, default=str) + "\n"
        # One writer at a time: events come from other threads too (progress ticks, the live director's
        # tools), and on Windows two appends at once can overwrite each other's start.
        with self._writing, (self.root / "log.jsonl").open("a", encoding="utf-8") as log:
            log.write(line)
        return entry

    def save_json(self, name: str, data: Any) -> Path:
        """A model or plain data as JSON in the run; logged as "saved"."""
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json", by_alias=True, exclude_none=True)
        p = self.path(name)
        p.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.event("saved", file=name)
        return p

    def add_file(self, source: Path | str, name: str) -> Path:
        """A copy of an outside file (a photo, a label) in the run."""
        p = self.path(name)
        shutil.copyfile(source, p)
        self.event("saved", file=name)
        return p

    def output(self, label: str, file: Path | str) -> None:
        """Marks a file in the run as one of its results ("video", "storyboard")."""
        self.outputs[label] = str(Path(file).resolve().relative_to(self.root.resolve())).replace("\\", "/")
        self.event("output", label=label, file=self.outputs[label])

    def finish(self, status: str = "done") -> dict:
        """Writes run.json; the status, length, model cost and outputs."""
        self.status = status
        calls = usage.calls()[self._usage_from:]
        summary = {"status": status, "seconds": round(time.time() - self.started, 2),
                   "model_calls": len(calls), "cached_calls": sum(c.cached for c in calls),
                   "cost": round(sum(c.cost for c in calls), 6), "outputs": self.outputs}
        self.event("finished", **summary)
        (self.root / "run.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary

    def _on_studio_call(self, method: str, params: dict, seconds: float, error) -> None:
        entry = {"method": method, "params": params, "seconds": seconds}
        if error:
            entry["error"] = error.message
        self.event("studio", **entry)

    def _on_model_call(self, call: usage.Call) -> None:
        self.event("model", call_kind=call.kind, model=call.model, cached=call.cached, seconds=call.seconds,
                   input_tokens=call.input_tokens, output_tokens=call.output_tokens, cost=round(call.cost, 6))


# --- Reading --------------------------------------------------------------------------------

def events(root: Path | str) -> list[dict]:
    """The run's events, in order; a line that isn't whole JSON (a log
    written before writes were locked could have one) is skipped."""
    path = Path(root) / "log.jsonl"
    return [entry for line in path.read_text(encoding="utf-8").splitlines() if (entry := parse_event(line))]


def parse_event(line: str) -> dict | None:
    """One log line as its event, or None if it's empty or not whole JSON."""
    try:
        entry = json.loads(line) if line.strip() else None
    except json.JSONDecodeError:
        return None
    return entry if isinstance(entry, dict) and "kind" in entry else None


def replay(root: Path | str, speed: float = 1.0) -> Iterator[dict]:
    """The run's events, each at its time (sped up by `speed`; 0 = no waiting)."""
    began = time.time()
    for entry in events(root):
        if speed > 0:
            wait = entry["t"] / speed - (time.time() - began)
            if wait > 0:
                time.sleep(wait)
        yield entry


def all_runs(base: Path = RUNS) -> list[Path]:
    return sorted((p for p in base.glob("*") if (p / "log.jsonl").exists()), reverse=True)


def _describe(entry: dict) -> str:
    rest = {k: v for k, v in entry.items() if k not in ("t", "time", "kind")}
    return f"{entry['t']:>8.2f}s  {entry['kind']:<10} " + " ".join(f"{k}={v}" for k, v in rest.items())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="List runs, show one, or replay it with its timing.")
    parser.add_argument("run", nargs="?", help="a run folder (default: list them; 'last' = the newest)")
    parser.add_argument("--replay", type=float, metavar="SPEED", help="print events at their times, SPEED times faster")
    args = parser.parse_args()
    if not args.run:
        for p in all_runs():
            summary = json.loads((p / "run.json").read_text()) if (p / "run.json").exists() else {"status": "running?"}
            print(f"{p.name:44} {summary.get('status'):8} {summary.get('seconds', 0):>8}s  ${summary.get('cost', 0):.4f}")
        sys.exit()
    root = all_runs()[0] if args.run == "last" else Path(args.run)
    for entry in (replay(root, args.replay) if args.replay else events(root)):
        print(_describe(entry), flush=True)
