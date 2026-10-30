"""3D models of products, found online: one search over several sources,
keeping only models we may use, and a download that comes with its credit.

    found = search("perfume bottle")          # [Candidate], every source, best first
    model = download(found[0])                # a .glb, with found[0].credit() to show
    product_glb = normalize(model, run.path("product.glb"), height=0.12)   # pipeline.studio.models

Sources (catalog/*.py), each with a free API and each model's licence:

    sketchfab   the largest library; search is open, downloading needs SKETCHFAB_API_TOKEN in .env
    objaverse   46,000 Sketchfab models in 1,156 categories (Allen Institute's dataset), downloaded
                from Hugging Face without an account; names and licences checked on Sketchfab
    polyhaven   500+ CC0 models, high quality, few retail products; real-world dimensions

Only CC0 (no conditions) and CC-BY (credit the author) are kept: changing a
model's colours makes a derivative, and the ads may be commercial, so
non-commercial and no-derivatives licences are out. Models with more faces
than MAX_FACES are skipped (too slow for a laptop GPU). Downloads are cached
in cache/models/, so a model is fetched once.

sets.py is the set library beside them: surfaces and light environments
(Poly Haven, CC0) for the pedestal, the backdrop and the light.
"""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .common import ALLOWED_LICENCES, CACHE, MAX_FACES, Candidate, CatalogError
from . import objaverse, polyhaven, sketchfab

SOURCES = {"sketchfab": sketchfab, "objaverse": objaverse, "polyhaven": polyhaven}


def search(query: str, limit: int = 12, sources: tuple[str, ...] = tuple(SOURCES)) -> list[Candidate]:
    """Models of `query` from every source, interleaved so each shows near
    the top, best first within a source; ones already found under another
    source (Objaverse's are Sketchfab's) once. A source that fails is skipped."""
    def one(name: str) -> list[Candidate]:
        try:
            return SOURCES[name].search(query, limit)
        except Exception:   # noqa: BLE001 -- one source down shouldn't stop the others
            return []

    with ThreadPoolExecutor(len(sources)) as pool:
        lists = list(pool.map(one, sources))
    out, seen = [], set()
    for rank in range(max((len(x) for x in lists), default=0)):
        for found in lists:
            if rank < len(found) and found[rank].key not in seen:
                seen.add(found[rank].key)
                out.append(found[rank])
    return out[:limit * len(sources)]


def download(candidate: Candidate) -> Path:
    """The candidate's model as a .glb in the cache (fetched once), with its
    credit written next to it (<file>.credit.json)."""
    return SOURCES[candidate.source].download(candidate)


__all__ = ["ALLOWED_LICENCES", "CACHE", "Candidate", "CatalogError", "MAX_FACES", "SOURCES", "download", "search"]
