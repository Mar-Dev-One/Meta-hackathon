"""What every source shares: a candidate model, the licences we accept,
where downloads go, and HTTP with a name and a timeout."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from pipeline.meta.config import ROOT

CACHE = ROOT / "cache" / "models"
MAX_FACES = 300_000
TIMEOUT = 60
HEADERS = {"User-Agent": "Meta-hackathon-Studio/1.0 (product ads; github.com/Mar-Dev-One/Meta-hackathon)"}

# Licence codes as Sketchfab names them, and how each is shown.
ALLOWED_LICENCES = {
    "cc0": ("CC0 1.0 (public domain)", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "by": ("CC BY 4.0 (credit the author)", "https://creativecommons.org/licenses/by/4.0/"),
}


class CatalogError(Exception):
    """A model couldn't be found or fetched; the message says why."""


@dataclass
class Candidate:
    source: str            # "sketchfab", "objaverse", "polyhaven"
    id: str                # the source's own id (Sketchfab's uid for Objaverse too)
    name: str
    author: str
    licence: str           # a key of ALLOWED_LICENCES
    page: str              # where a person can see it
    thumbnail: str         # an image URL
    faces: int = 0         # 0 when the source doesn't say
    needs_token: bool = False   # downloading needs an account token the app doesn't have
    size_m: list[float] | None = None   # real-world size if the source knows it (x, y, z meters)

    @property
    def key(self) -> str:
        """The same model across sources (Objaverse's are Sketchfab's)."""
        return f"sketchfab:{self.id}" if self.source in ("sketchfab", "objaverse") else f"{self.source}:{self.id}"

    def credit(self) -> str:
        label, _ = ALLOWED_LICENCES[self.licence]
        return f"“{self.name}” by {self.author}, {self.page}, {label}"

    def to_json(self) -> dict:
        label, url = ALLOWED_LICENCES[self.licence]
        return asdict(self) | {"licence_label": label, "licence_url": url, "credit": self.credit()}


# A dropped connection, a timeout or a server error (5xx) is tried again after
# each of these waits (seconds): about 3 minutes, then it fails.
OUTAGE_WAITS = (5, 15, 30, 60, 90)


class _Outage(Exception):
    """A server error worth trying again."""


def _patiently(attempt):
    """attempt()'s result, an outage waited out (OUTAGE_WAITS)."""
    for wait in (*OUTAGE_WAITS, None):
        try:
            return attempt()
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError, _Outage) as e:
            if wait is None:
                raise CatalogError(f"no answer after {sum(OUTAGE_WAITS)} s of trying: {e}") from e
            time.sleep(wait)


def get(url: str, **kwargs) -> requests.Response:
    headers = HEADERS | kwargs.pop("headers", {})

    def attempt():
        response = requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
        if response.status_code >= 500:
            raise _Outage(f"{url}: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise CatalogError(f"{url}: HTTP {response.status_code} {response.text[:200]}")
        return response
    return _patiently(attempt)


def fetch(url: str, path: Path, **kwargs) -> Path:
    """`url` saved at `path` (folders made), streamed; a download cut off is
    started again (only a whole file takes the name)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = HEADERS | kwargs.pop("headers", {})

    def attempt():
        with requests.get(url, headers=headers, timeout=TIMEOUT, stream=True, **kwargs) as r:
            if r.status_code >= 500:
                raise _Outage(f"{url}: HTTP {r.status_code}")
            if r.status_code >= 400:
                raise CatalogError(f"{url}: HTTP {r.status_code}")
            partial = path.with_suffix(path.suffix + ".part")
            with partial.open("wb") as out:
                for chunk in r.iter_content(1 << 16):
                    out.write(chunk)
            partial.replace(path)
        return path
    return _patiently(attempt)


def save_credit(candidate: Candidate, model: Path) -> None:
    model.with_suffix(".credit.json").write_text(json.dumps(candidate.to_json(), indent=2), encoding="utf-8")
