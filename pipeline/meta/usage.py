"""What every model call cost: tokens, images, seconds, dollars, and whether
the cache answered it. One process-wide ledger; a run reads its summary.

    from pipeline.meta import usage
    usage.reset()
    ... calls ...
    print(usage.summary())
"""

import threading
import time
from dataclasses import asdict, dataclass, field

from . import config


@dataclass
class Call:
    kind: str                # "text", "tools", "segment", "image", "transcribe"
    model: str
    cached: bool
    seconds: float
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    units: int = 0           # images generated or segmented, seconds of audio
    cost: float = 0.0        # dollars; 0 for cache hits
    when: float = field(default_factory=time.time)


_calls: list[Call] = []
_listeners: list = []   # functions(Call), told of every call (an open run logs them)
_lock = threading.Lock()


def add_listener(fn) -> None:
    with _lock:
        _listeners.append(fn)


def remove_listener(fn) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def token_cost(model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> float:
    price = config.TOKEN_PRICES.get(model)
    if not price:
        return 0.0   # e.g. Muse Spark Open on Baseten: billed there, not here
    per_input, per_cached, per_output = price
    fresh = max(input_tokens - cached_input_tokens, 0)
    return (fresh * per_input + cached_input_tokens * per_cached + output_tokens * per_output) / 1e6


def record(call: Call) -> Call:
    with _lock:
        _calls.append(call)
        listeners = list(_listeners)
    for fn in listeners:
        fn(call)
    return call


def calls() -> list[Call]:
    with _lock:
        return list(_calls)


def reset() -> None:
    with _lock:
        _calls.clear()


def summary() -> dict:
    """Totals overall and per model."""
    rows = calls()
    by_model: dict[str, dict] = {}
    for c in rows:
        m = by_model.setdefault(c.model, {"calls": 0, "cached": 0, "input_tokens": 0, "output_tokens": 0,
                                          "units": 0, "cost": 0.0, "seconds": 0.0})
        m["calls"] += 1
        m["cached"] += c.cached
        m["input_tokens"] += c.input_tokens
        m["output_tokens"] += c.output_tokens
        m["units"] += c.units
        m["cost"] += c.cost
        m["seconds"] += c.seconds
    return {
        "calls": len(rows),
        "cached": sum(c.cached for c in rows),
        "cost": round(sum(c.cost for c in rows), 6),
        "seconds": round(sum(c.seconds for c in rows), 2),
        "by_model": {k: {**v, "cost": round(v["cost"], 6), "seconds": round(v["seconds"], 2)} for k, v in by_model.items()},
    }


def as_dicts() -> list[dict]:
    return [asdict(c) for c in calls()]
