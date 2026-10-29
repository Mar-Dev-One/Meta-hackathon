"""Poly Haven (polyhaven.com): 500+ models, all CC0, with real-world sizes.
Mostly props and household objects; searched by name, tags and categories.
Its models come as glTF with separate textures, packed here into one GLB."""

import json
import re
import time
from pathlib import Path

import trimesh

from .common import CACHE, Candidate, CatalogError, fetch, get, save_credit

API = "https://api.polyhaven.com"
RESOLUTION = "1k"          # texture size: plenty for a product a few hundred pixels tall in a preview
CATALOGUE_AGE = 24 * 3600  # seconds before the catalogue is fetched again


def catalogue() -> dict:
    """Every model, cached for a day: {id: {name, tags, categories, authors, dimensions (mm)}}."""
    path = CACHE / "polyhaven" / "catalogue.json"
    if not path.exists() or time.time() - path.stat().st_mtime > CATALOGUE_AGE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(get(f"{API}/assets", params={"t": "models"}).json()), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2}


def search(query: str, limit: int = 12) -> list[Candidate]:
    """Models whose name, tags or categories share words with `query`, the
    most shared first (a word in the name counts double)."""
    wanted = _words(query)
    scored = []
    for key, m in catalogue().items():
        name = _words(m["name"])
        rest = _words(" ".join(m.get("tags", []) + m.get("categories", [])))
        score = 2 * len(wanted & name) + len(wanted & rest)
        if score:
            scored.append((score, key, m))
    scored.sort(key=lambda s: (-s[0], s[1]))
    out = []
    for _, key, m in scored[:limit]:
        dims = m.get("dimensions")
        out.append(Candidate(source="polyhaven", id=key, name=m["name"], author=", ".join(m.get("authors", {})) or "Poly Haven",
                             licence="cc0", page=f"https://polyhaven.com/a/{key}",
                             thumbnail=f"https://cdn.polyhaven.com/asset_img/thumbs/{key}.png?width=256",
                             faces=m.get("polycount", 0), size_m=[round(d / 1000, 4) for d in dims] if dims else None))
    return out


def download(c: Candidate) -> Path:
    """The glTF and its textures at RESOLUTION, packed into one GLB."""
    path = CACHE / "polyhaven" / f"{c.id}.glb"
    if not path.exists():
        files = get(f"{API}/files/{c.id}").json().get("gltf", {})
        if RESOLUTION not in files:
            raise CatalogError(f"Poly Haven has no {RESOLUTION} glTF of {c.id}: {list(files)}")
        entry = files[RESOLUTION]["gltf"]
        folder = CACHE / "polyhaven" / c.id
        main = fetch(entry["url"], folder / Path(entry["url"]).name)
        for relative, item in entry.get("include", {}).items():
            fetch(item["url"], folder / relative)
        trimesh.load(str(main), force="scene").export(str(path), file_type="glb")
    save_credit(c, path)
    return path
