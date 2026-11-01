"""The app's backend: start an ad from a photo and a brief, follow it as it
happens, open any run that's already done.

    python -m app                      # http://127.0.0.1:8000: the page (app/static/index.html)
    curl -F photo=@Assets/photos/mira_jar.png -F "brief=Face cream, calm and bright, 10 seconds." \\
         -F category=jar -F format=vertical http://127.0.0.1:8000/runs
    curl -N http://127.0.0.1:8000/runs/<id>/events

    GET  /                           the page: start an ad, watch it, open any run
    POST /runs                       a photo (file) and a brief: queues an ad (pipeline.agents.producer);
                                     format = horizontal, vertical or both (default); director = storyboard
                                     (default: Spark plans, code builds) or live (Spark makes the film with
                                     every Studio command);
                                     optionally a 3D model of the product: model_pick (a search result's
                                     JSON) or model_file (a .glb)
    GET  /models/search?q=           3D models of a product online, ones we may use (pipeline.catalog)
    GET  /runs                       every run, newest first: status, brief, outputs
    GET  /runs/{id}                  one run: its summary (run.json) and outputs
    GET  /runs/{id}/events           its log as Server-Sent Events: followed live while it runs;
                                     ?speed=1 replays a finished one with its timing (2 twice as fast)
    GET  /runs/{id}/files/{path}     a file in it: frames, contact sheets, the videos
    POST /runs/{id}/cancel           stops a run (queued or running): its status becomes "cancelled"
    POST /runs/{id}/again            queues the run's ad again from its inputs (pipeline.runs.inputs),
                                     optionally with a new brief or format: a new run
    GET  /gallery                    every finished ad, newest first: its videos, end card, time and cost

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
from pipeline.agents.producer import DIRECTORS, FORMATS, make_ad
from pipeline.catalog.common import Candidate
from pipeline.runs import RUNS, Run, all_runs, events, inputs, parse_event
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
    director: str = "storyboard"
    model_pick: Candidate | None = None   # a search result, downloaded by the worker
    model_file: Path | None = None        # an uploaded model


jobs: "queue.Queue[Job]" = queue.Queue()
waiting: list[str] = []          # run ids queued, in order
active: dict[str, str] = {}      # run id -> "running" while the worker has it
cancelled: set[str] = set()      # queued runs cancelled before the worker got to them
current: dict[str, tuple] = {}   # the running run's id -> (its event loop, its task), to cancel it


def _work() -> None:
    """The worker thread: one job at a time, each with a fresh Studio."""
    while True:
        job = jobs.get()
        rid = job.run.root.name
        waiting.remove(rid)
        if rid in cancelled:
            continue
        active[rid] = "running"
        try:
            asyncio.run(_running(rid, job))
        except BaseException:   # noqa: BLE001 -- the run's log has it ("failed", "cancelled"); the worker carries on
            pass
        finally:
            active.pop(rid, None)
            current.pop(rid, None)


async def _running(rid: str, job: Job) -> None:
    """The job, its loop and task kept so a cancel can reach it from the server's thread."""
    task = asyncio.current_task()
    current[rid] = (asyncio.get_running_loop(), task)
    await _make(job)


async def _make(job: Job) -> None:
    with job.run:   # first, so a Studio that won't start is the run's "failed", with why
        async with Studio() as studio:
            model, credit = job.model_file, None
            if job.model_pick:
                job.run.event("model_download", source=job.model_pick.source, name=job.model_pick.name)
                model, credit = catalog.download(job.model_pick), job.model_pick.to_json()
            await make_ad(studio, job.run, job.brief, job.photo, job.category, job.size, video=job.video,
                          critic=job.critic, format=job.format, model=model, credit=credit,
                          director=job.director)


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
    if rid in cancelled:
        return "cancelled"
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
        if e["kind"] == "queued" and not first:   # one cancelled while queued never got a brief event
            first = {"text": e.get("brief")}
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
                critic: bool = Form(False), video: bool = Form(True), size: int = Form(1080),
                format: str = Form("both"), director: str = Form("storyboard"), model_pick: str = Form(""),
                model_file: UploadFile | None = File(None)) -> dict:
    """Queues an ad: the photo and brief in, a run id back to follow."""
    name = Path(photo.filename or "photo.png").name
    if Path(name).suffix.lower() not in PHOTO_TYPES:
        raise HTTPException(422, f"the photo must be one of {', '.join(PHOTO_TYPES)}")
    if not brief.strip():
        raise HTTPException(422, "the brief is empty")
    if format not in FORMATS:
        raise HTTPException(422, f"the format must be one of {', '.join(FORMATS)}")
    if director not in DIRECTORS:
        raise HTTPException(422, f"the director must be one of {', '.join(DIRECTORS)}")
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
              format=format, director=director, model=pick.name if pick else model_name or None)
    jobs.put(Job(run, upload, brief.strip(), category, critic, video, size, format, director, pick, model_upload))
    return {"id": rid, "status": "queued", "position": len(waiting), "events": f"/runs/{rid}/events"}


@app.post("/runs/{rid}/cancel")
def cancel(rid: str) -> dict:
    """Stops a run: a queued one never starts; a running one stops at its next
    step (a model call or render under way finishes first), its Studio closed."""
    root = _root(rid)
    if rid in waiting:
        cancelled.add(rid)
        with Run(root) as run:
            run.event("cancelled")
            run.finish("cancelled")
        return {"id": rid, "status": "cancelled"}
    if rid in current:
        loop, task = current[rid]
        loop.call_soon_threadsafe(task.cancel)
        return {"id": rid, "status": "cancelling"}
    raise HTTPException(409, f"{rid} isn't queued or running ({_status(root)})")


@app.post("/runs/{rid}/again", status_code=202)
def again(rid: str, brief: str = Form(""), format: str = Form("")) -> dict:
    """The run's ad made again from its inputs, as a new run, with a new brief
    or format if given (the rest as it was). What the first one had done is
    cached (Spark's answers, the models), so it picks up quickly."""
    given = inputs(_root(rid))
    if brief.strip():
        given["brief"] = brief.strip()
    if format:
        if format not in FORMATS:
            raise HTTPException(422, f"the format must be one of {', '.join(FORMATS)}")
        given["format"] = format
    run = Run.create(f"ad-{given['photo'].stem}")
    photo = run.path("upload", given["photo"].name)
    shutil.copyfile(given["photo"], photo)
    model = None
    if given["model"]:
        model = run.path("upload", given["model"].name)
        shutil.copyfile(given["model"], model)
    new = run.root.name
    waiting.append(new)
    run.event("queued", position=len(waiting), brief=given["brief"], category=given["category"], critic=given["critic"],
              video=given["video"], format=given["format"], director=given["director"],
              model=model.name if model else None, again=rid)
    jobs.put(Job(run, photo, given["brief"], given["category"], given["critic"], given["video"], given["short"],
                 given["format"], given["director"], None, model))
    return {"id": new, "status": "queued", "position": len(waiting), "again": rid, "events": f"/runs/{new}/events"}


@app.get("/gallery")
def gallery(limit: int = 60) -> list[dict]:
    """Every finished ad, newest first: its videos (by aspect), its end card,
    its brief, time and cost."""
    out = []
    for root in all_runs():
        summary = root / "run.json"
        if not summary.exists():
            continue
        info = json.loads(summary.read_text(encoding="utf-8"))
        videos = {k.removeprefix("video_"): v for k, v in info.get("outputs", {}).items()
                  if k.startswith("video") and (root / v).exists()}
        if info.get("status") != "done" or not videos:
            continue
        card = next(iter(sorted(root.glob("final/*_card.png"))), None)
        out.append(_card(root) | {"videos": videos, "poster": card.relative_to(root).as_posix() if card else None})
        if len(out) >= limit:
            break
    return out


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
        text = log.read_text(encoding="utf-8")
        # Only whole lines: the worker may be halfway through writing the last one.
        lines = text[:text.rfind("\n") + 1].splitlines()
        for line in lines[sent:]:
            entry = parse_event(line)
            if entry is None:   # empty, or a broken line in an old log: skipped, not the whole stream
                sent += 1
                continue
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
