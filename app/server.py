"""The app's backend: start an ad from a photo and a brief, follow it as it
happens, open any run that's already done.

    python -m app                      # http://127.0.0.1:8000: the page (app/static/index.html)
    curl -F photo=@Assets/photos/mira_jar.png -F "brief=Face cream, calm and bright, 10 seconds." \\
         -F category=jar -F format=vertical http://127.0.0.1:8000/runs
    curl -N http://127.0.0.1:8000/runs/<id>/events

    GET  /                           the page: start an ad, watch it, open any run
    POST /runs                       a photo (file) and a brief: queues an ad (pipeline.agents.producer);
                                     format = horizontal, vertical or both (default); optionally a 3D model of
                                     the product: model_pick (a search result's JSON) or model_file (a .glb)
    GET  /models/search?q=           3D models of a product online, ones we may use (pipeline.catalog)
    GET  /runs                       every run, newest first: status, brief, outputs
    GET  /runs/{id}                  one run: its summary (run.json) and outputs
    GET  /runs/{id}/events           its log as Server-Sent Events: followed live while it runs;
                                     ?speed=1 replays a finished one with its timing (2 twice as fast)
    GET  /runs/{id}/files/{path}     a file in it: frames, contact sheets, the videos

Runs go one at a time (one renderer, one GPU) through a worker thread with
its own event loop and its own Studio: the agents' model calls block, and in
the server's loop they'd stall every stream. The worker writes the run's
log; the streams read it, so a live run, a finished one and a replay are
the same thing to a client. A run is its folder in runs/, named by its id.
"""

import asyncio
import json
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from pipeline import catalog
from pipeline.agents.producer import FORMATS, make_ad
from pipeline.catalog.common import Candidate
from pipeline.runs import RUNS, Run, all_runs, events
from pipeline.studio import Studio

PAGE = Path(__file__).with_name("static") / "index.html"
POLL = 0.25          # seconds between looks at a live run's log
HEARTBEAT = 15.0     # seconds between keep-alive comments on a quiet stream
PHOTO_TYPES = (".png", ".jpg", ".jpeg", ".webp")
MODEL_TYPES = (".glb",)

app = FastAPI(title="Studio", description="Product photo and brief in, finished ad out.")


@dataclass
class Job:
    run: Run
    photo: Path
    brief: str
    category: str
    critic: bool
    video: bool
    size: int
    format: str
    model_pick: Candidate | None = None   # a search result, downloaded by the worker
    model_file: Path | None = None        # an uploaded model


jobs: "queue.Queue[Job]" = queue.Queue()
waiting: list[str] = []          # run ids queued, in order
active: dict[str, str] = {}      # run id -> "running" while the worker has it


def _work() -> None:
    """The worker thread: one job at a time, each with a fresh Studio."""
    while True:
        job = jobs.get()
        rid = job.run.root.name
        waiting.remove(rid)
        active[rid] = "running"
        try:
            asyncio.run(_make(job))
        except Exception:   # noqa: BLE001 -- the run's log has it ("failed"); the worker carries on
            pass
        finally:
            active.pop(rid, None)


async def _make(job: Job) -> None:
    async with Studio() as studio:
        with job.run:
            model, credit = job.model_file, None
            if job.model_pick:
                job.run.event("model_download", source=job.model_pick.source, name=job.model_pick.name)
                model, credit = catalog.download(job.model_pick), job.model_pick.to_json()
            await make_ad(studio, job.run, job.brief, job.photo, job.category, job.size, video=job.video,
                          critic=job.critic, format=job.format, model=model, credit=credit)


threading.Thread(target=_work, name="producer", daemon=True).start()


# --- Runs ---------------------------------------------------------------------------------


def _root(rid: str) -> Path:
    root = (RUNS / rid).resolve()
    if root.parent != RUNS.resolve() or not (root / "log.jsonl").exists():
        raise HTTPException(404, f"no run {rid!r}")
    return root


def _status(root: Path) -> str:
    """queued, running, done or failed; "stopped" for a run that ended without
    saying (the process was killed)."""
    rid = root.name
    if rid in active:
        return active[rid]
    if rid in waiting:
        return "queued"
    summary = root / "run.json"
    if summary.exists():
        return json.loads(summary.read_text(encoding="utf-8")).get("status", "done")
    return "stopped"


def _card(root: Path) -> dict:
    """What a list of runs shows of one."""
    first = {}
    for e in events(root)[:40]:
        if e["kind"] == "brief":
            first = e
            break
    summary = root / "run.json"
    info = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    return {"id": root.name, "status": _status(root), "brief": first.get("text"), "photo": first.get("photo"),
            "outputs": info.get("outputs", {}), "seconds": info.get("seconds"), "cost": info.get("cost"),
            "events": f"/runs/{root.name}/events"}


@app.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})


@app.get("/models/search")
def search_models(q: str, limit: int = 12) -> list[dict]:
    """3D models of `q` online that we may use (CC0, CC-BY), from every
    source, best first; each with its thumbnail, licence and credit."""
    if not q.strip():
        raise HTTPException(422, "nothing to search for")
    return [c.to_json() for c in catalog.search(q.strip(), limit=min(max(limit, 1), 24))]


def _pick(text: str) -> Candidate:
    """A search result sent back by the page, checked: a known source, a
    licence we accept, and, for Sketchfab, a token to download it with."""
    try:
        data = json.loads(text)
        pick = Candidate(**{k: data[k] for k in Candidate.__dataclass_fields__ if k in data})
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"model_pick isn't a search result: {e}")
    if pick.source not in catalog.SOURCES or pick.licence not in catalog.ALLOWED_LICENCES:
        raise HTTPException(422, f"model_pick: unknown source {pick.source!r} or licence {pick.licence!r}")
    if pick.source == "sketchfab" and not catalog.sketchfab.token():
        raise HTTPException(422, "downloading from Sketchfab needs SKETCHFAB_API_TOKEN in .env "
                                 "(sketchfab.com > Settings > Password & API); pick another model or add it")
    return pick


@app.post("/runs", status_code=202)
async def start(photo: UploadFile = File(...), brief: str = Form(...), category: str = Form("product"),
                critic: bool = Form(True), video: bool = Form(True), size: int = Form(1080),
                format: str = Form("both"), model_pick: str = Form(""),
                model_file: UploadFile | None = File(None)) -> dict:
    """Queues an ad: the photo and brief in, a run id back to follow."""
    name = Path(photo.filename or "photo.png").name
    if Path(name).suffix.lower() not in PHOTO_TYPES:
        raise HTTPException(422, f"the photo must be one of {', '.join(PHOTO_TYPES)}")
    if not brief.strip():
        raise HTTPException(422, "the brief is empty")
    if format not in FORMATS:
        raise HTTPException(422, f"the format must be one of {', '.join(FORMATS)}")
    pick = _pick(model_pick) if model_pick.strip() else None
    model_name = Path(model_file.filename or "").name if model_file and model_file.filename else ""
    if model_name and Path(model_name).suffix.lower() not in MODEL_TYPES:
        raise HTTPException(422, f"the model must be a {', '.join(MODEL_TYPES)} file")
    run = Run.create(f"ad-{Path(name).stem}")
    upload = run.path("upload", name)
    with upload.open("wb") as out:
        shutil.copyfileobj(photo.file, out)
    model_upload = None
    if model_name and not pick:
        model_upload = run.path("upload", model_name)
        with model_upload.open("wb") as out:
            shutil.copyfileobj(model_file.file, out)
    rid = run.root.name
    waiting.append(rid)
    run.event("queued", position=len(waiting), brief=brief, category=category, critic=critic, video=video,
              format=format, model=pick.name if pick else model_name or None)
    jobs.put(Job(run, upload, brief.strip(), category, critic, video, size, format, pick, model_upload))
    return {"id": rid, "status": "queued", "position": len(waiting), "events": f"/runs/{rid}/events"}


@app.get("/runs")
def list_runs(limit: int = 50) -> list[dict]:
    return [_card(root) for root in all_runs()[:limit]]


@app.get("/runs/{rid}")
def get_run(rid: str) -> dict:
    root = _root(rid)
    summary = root / "run.json"
    return _card(root) | {"summary": json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else None}


@app.get("/runs/{rid}/files/{path:path}")
def get_file(rid: str, path: str) -> FileResponse:
    root = _root(rid)
    file = (root / path).resolve()
    if root not in file.parents or not file.is_file():
        raise HTTPException(404, f"no file {path!r} in {rid}")
    return FileResponse(file)


# --- Events -------------------------------------------------------------------------------


async def _stream(root: Path, speed: float, start: int):
    """The run's events from line `start`, as SSE: while it's live, new ones
    as they're written; with `speed`, paced by their times."""
    log = root / "log.jsonl"
    sent, began, last = start, time.monotonic(), time.monotonic()
    first_t = None
    while True:
        lines = log.read_text(encoding="utf-8").splitlines()
        for line in lines[sent:]:
            if not line.strip():
                sent += 1
                continue
            entry = json.loads(line)
            if speed > 0:
                first_t = entry["t"] if first_t is None else first_t
                wait = (entry["t"] - first_t) / speed - (time.monotonic() - began)
                if wait > 0:
                    await asyncio.sleep(wait)
            sent += 1
            last = time.monotonic()
            yield f"id: {sent}\nevent: {entry['kind']}\ndata: {line}\n\n"
        live = _status(root) in ("queued", "running")
        if not live and sent >= len(lines):
            yield "event: end\ndata: {}\n\n"
            return
        if time.monotonic() - last > HEARTBEAT:
            last = time.monotonic()
            yield ": still here\n\n"
        await asyncio.sleep(POLL)


@app.get("/runs/{rid}/events")
async def stream_events(rid: str, speed: float = 0.0, start: int = 0) -> StreamingResponse:
    """Every event of the run as it happens (or replayed: `speed` 1 is real
    time). Each is an SSE message named by its kind, its data the event's
    JSON, its id its line; `start` resumes after that id. The stream ends
    with an "end" message once the run is over and everything's sent."""
    return StreamingResponse(_stream(_root(rid), speed, max(start, 0)), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
