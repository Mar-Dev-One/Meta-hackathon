"""Runs every smoke test in order through pipeline.meta and writes
out/summary.md: what worked, what each model answered, and the cost. Run it
twice: the second run should be answered entirely from the cache (cost $0).

    python pipeline/meta/smoke/run_all.py           # cached answers where there are some
    python pipeline/meta/smoke/run_all.py --fresh   # every call made again (META_CACHE=off)
"""

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if "--fresh" in sys.argv:
    os.environ["META_CACHE"] = "off"

from _common import OUT, Skip  # noqa: E402

from pipeline.meta import MissingKey, usage  # noqa: E402


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    rows = []
    for path in sorted(HERE.glob("[0-9][0-9]_*.py")):
        print(f"--- {path.stem}")
        try:
            status, details = "ok", load(path).run()
        except (Skip, MissingKey) as e:
            status, details = "skipped", {"reason": str(e)}
        except Exception as e:  # noqa: BLE001 -- a smoke test reports every failure
            status, details = "FAILED", {"error": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
        for k, v in details.items():
            print(f"  {k}: {v}")
        rows.append((path.stem, status, details))

    totals = usage.summary()
    print(f"\n{totals['calls']} calls, {totals['cached']} from the cache, ${totals['cost']:.4f}, {totals['seconds']}s")
    for model, m in totals["by_model"].items():
        print(f"  {model:28} {m['calls']} calls ({m['cached']} cached)  in {m['input_tokens']} out {m['output_tokens']}"
              f"  ${m['cost']:.4f}")

    lines = ["# Smoke test summary", ""]
    for name, status, details in rows:
        lines += [f"## {name}: {status}", ""]
        lines += [f"- **{k}:** {json.dumps(v) if isinstance(v, (dict, list)) else v}" for k, v in details.items()]
        lines.append("")
    lines += ["## Usage", "", "```json", json.dumps(totals, indent=2), "```"]
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"summary: {OUT / 'summary.md'}")
    return 1 if any(status == "FAILED" for _, status, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
