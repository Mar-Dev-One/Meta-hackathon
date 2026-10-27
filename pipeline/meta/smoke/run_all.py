"""Runs every smoke test in order and writes out/summary.md: what worked, how
fast, and what each model answered. A test that can't run (no key, missing
input) is skipped, not failed."""

import importlib.util
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import OUT, Skip  # noqa: E402


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
            result = load(path).run()
            status = "ok"
            details = result
        except Skip as e:
            status, details = "skipped", {"reason": str(e)}
        except Exception as e:  # noqa: BLE001 -- a smoke test reports every failure
            status, details = "FAILED", {"error": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
        for k, v in details.items():
            print(f"  {k}: {v}")
        rows.append((path.stem, status, details))

    lines = ["# Smoke test summary", ""]
    for name, status, details in rows:
        lines.append(f"## {name}: {status}")
        lines.append("")
        for k, v in details.items():
            v = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            lines.append(f"- **{k}:** {v}")
        lines.append("")
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nsummary: {OUT / 'summary.md'}")
    return 1 if any(status == "FAILED" for _, status, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
