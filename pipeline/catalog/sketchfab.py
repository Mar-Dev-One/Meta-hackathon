"""Sketchfab (sketchfab.com): its search is open; downloading a model needs
an account's API token (Settings > Password & API) as SKETCHFAB_API_TOKEN
in .env. Results are downloadable models under CC0 or CC-BY only."""

import json
import os
import time
from pathlib import Path

from pipeline.meta import config  # noqa: F401 -- loads .env, where the token lives

from .common import ALLOWED_LICENCES, CACHE, MAX_FACES, Candidate, CatalogError, fetch, get, save_credit

API = "https://api.sketchfab.com/v3"


def token() -> str | None:
    return os.environ.get("SKETCHFAB_API_TOKEN", "").strip() or None


def _thumbnail(model: dict, width: int = 256) -> str:
    images = sorted(model.get("thumbnails", {}).get("images", []), key=lambda i: abs(i["width"] - width))
    return images[0]["url"] if images else ""


def candidate(model: dict, licence: str, source: str = "sketchfab") -> Candidate:
    return Candidate(source=source, id=model["uid"], name=model.get("name") or "untitled",
                     author=(model.get("user") or {}).get("displayName") or (model.get("user") or {}).get("username", "?"),
                     licence=licence, page=model.get("viewerUrl") or f"https://sketchfab.com/3d-models/{model['uid']}",
                     thumbnail=_thumbnail(model), faces=model.get("faceCount") or 0,
                     needs_token=source == "sketchfab" and token() is None)


def search(query: str, limit: int = 12) -> list[Candidate]:
    """Downloadable models matching `query`, CC-BY and CC0 interleaved, by
    Sketchfab's relevance."""
    per = {}
    for licence in ALLOWED_LICENCES:
        found = get(f"{API}/search", params={"type": "models", "q": query, "downloadable": "true",
                                             "license": licence, "max_face_count": MAX_FACES,
                                             "count": limit}).json()["results"]
        per[licence] = [candidate(m, licence) for m in found]
    out = []
    for i in range(limit):
        for licence in ALLOWED_LICENCES:
            if i < len(per[licence]):
                out.append(per[licence][i])
    return out[:limit]


INFO_AGE = 7 * 24 * 3600   # seconds a model's details are kept: Sketchfab limits how often it's asked


def model_info(uid: str) -> dict:
    """A model's public details (name, author, licence, thumbnails), no
    token; kept on disk for a week, so repeated searches don't ask again."""
    path = CACHE / "sketchfab" / "info" / f"{uid}.json"
    if path.exists() and time.time() - path.stat().st_mtime < INFO_AGE:
        return json.loads(path.read_text(encoding="utf-8"))
    info = get(f"{API}/models/{uid}").json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info), encoding="utf-8")
    return info


def download(c: Candidate) -> Path:
    path = CACHE / "sketchfab" / f"{c.id}.glb"
    if not path.exists():
        key = token()
        if not key:
            raise CatalogError("downloading from Sketchfab needs an API token: add SKETCHFAB_API_TOKEN to .env "
                               "(sketchfab.com > Settings > Password & API)")
        links = get(f"{API}/models/{c.id}/download", headers={"Authorization": f"Token {key}"}).json()
        if "glb" not in links:
            raise CatalogError(f"Sketchfab has no GLB of {c.name!r} ({c.id}): only {list(links)}")
        fetch(links["glb"]["url"], path)
    save_credit(c, path)
    return path
