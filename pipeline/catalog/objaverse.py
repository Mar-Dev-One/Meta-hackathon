"""Objaverse (Allen Institute, objaverse.allenai.org): Sketchfab models,
here its LVIS subset, 46,000 objects sorted into 1,156 everyday categories
("cellular_telephone", "beer_bottle", "box"), downloaded from its Hugging
Face dataset without an account. A query is matched to categories; each
model's name, author and licence are checked on Sketchfab today (open, no
token), and only CC0 and CC-BY ones that are still up are kept."""

import gzip
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .common import ALLOWED_LICENCES, CACHE, MAX_FACES, Candidate, CatalogError, fetch, get, save_credit
from .sketchfab import candidate, model_info

DATASET = "https://huggingface.co/datasets/allenai/objaverse/resolve/main"
CHECK = 40   # candidates looked up on Sketchfab per search, at most

# Product words people use for LVIS's category names.
SYNONYMS = {
    "smartphone": ["cellular_telephone"], "phone": ["cellular_telephone", "telephone"],
    "mobile": ["cellular_telephone"], "perfume": ["perfume"], "fragrance": ["perfume"],
    "soda": ["can", "soda_water", "beer_can"], "drink": ["can", "bottle", "beer_bottle"],
    "cream": ["jar"], "skincare": ["jar", "bottle"], "lotion": ["bottle", "jar"], "cosmetic": ["jar", "bottle"],
    "sneaker": ["shoe", "sneaker"], "trainer": ["shoe"], "headphones": ["earphone", "headset"],
    "earbuds": ["earphone"], "watch": ["watch", "wristwatch"], "laptop": ["laptop_computer"],
    "packaging": ["box", "carton"], "box": ["box", "carton"], "oil": ["bottle"], "wine": ["wine_bottle"],
}


def _cached(name: str) -> Path:
    path = CACHE / "objaverse" / name
    if not path.exists():
        fetch(f"{DATASET}/{name}", path)
    return path


def categories() -> dict[str, list[str]]:
    """LVIS category -> Objaverse uids (0.9 MB, fetched once)."""
    return json.loads(gzip.decompress(_cached("lvis-annotations.json.gz").read_bytes()))


def object_paths() -> dict[str, str]:
    """uid -> its GLB's path in the dataset (20 MB, fetched once)."""
    return json.loads(gzip.decompress(_cached("object-paths.json.gz").read_bytes()))


def matching(query: str, cats: dict[str, list[str]]) -> list[str]:
    """The categories `query` names: its words (and their synonyms) against
    the category names' words, the best match first."""
    words = [w for w in re.split(r"[^a-z0-9]+", query.lower()) if len(w) > 2]
    wanted = set(words) | {w.rstrip("s") for w in words}
    names = set()
    for w in words:
        names.update(SYNONYMS.get(w, []))
    scored = []
    for cat in cats:
        cat_words = set(re.split(r"[^a-z0-9]+", cat.lower())) - {""}
        score = (3 if cat in names else 0) + len(wanted & cat_words)
        if score:
            scored.append((score, cat))
    return [cat for _, cat in sorted(scored, key=lambda s: (-s[0], s[1]))]


def search(query: str, limit: int = 12) -> list[Candidate]:
    cats = categories()
    uids: list[str] = []
    for cat in matching(query, cats)[:4]:
        uids += [u for u in cats[cat] if u not in uids]
    uids = uids[:CHECK]

    def look(uid: str) -> Candidate | None:
        try:
            model = model_info(uid)
        except CatalogError:
            return None   # taken down since the dataset was made
        licence = ((model.get("license") or {}).get("slug") or "").lower()
        if licence not in ALLOWED_LICENCES or (model.get("faceCount") or 0) > MAX_FACES:
            return None
        return candidate(model, licence, source="objaverse")

    with ThreadPoolExecutor(8) as pool:
        found = [c for c in pool.map(look, uids) if c]
    return found[:limit]


def download(c: Candidate) -> Path:
    path = CACHE / "objaverse" / "glbs" / f"{c.id}.glb"
    if not path.exists():
        relative = object_paths().get(c.id)
        if not relative:
            raise CatalogError(f"{c.id} isn't in Objaverse's object paths")
        fetch(f"{DATASET}/{relative}", path)
    save_credit(c, path)
    return path
