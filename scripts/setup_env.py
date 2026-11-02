"""The API keys in .env: asks for each one that's missing (typed hidden),
keeps the ones already there, and writes .env from .env.example's layout.
Run by start.bat; on its own:

    python scripts/setup_env.py           # ask only for missing keys
    python scripts/setup_env.py --ask     # ask for every key again (Enter keeps the current one)

Exits 1 if a required key is still missing (the app runs, but can't make ads).
"""

import argparse
import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV, EXAMPLE = ROOT / ".env", ROOT / ".env.example"

# name: (required, what it's for, where to get it)
KEYS = {
    "MODEL_API_KEY": (True, "the Meta Model API: Muse Spark, SAM 3.1, Muse Image, Muse Voice",
                      "https://dev.meta.ai"),
    "BASETEN_API_KEY": (False, "Muse Spark Open on Baseten, for the critic (--critic)",
                        "https://app.baseten.co/settings/api_keys"),
    "SKETCHFAB_API_TOKEN": (False, "downloading 3D models from Sketchfab (without it: Objaverse and Poly Haven)",
                            "sketchfab.com > Settings > Password & API"),
}
LINE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=(.*)$")


def read(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if m := LINE.match(line):
                values[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return values


def write(values: dict[str, str]) -> None:
    """.env in .env.example's layout (its comments kept), any other key already in .env after it."""
    template = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.exists() else ""
    lines, done = [], set()
    for line in template.splitlines():
        if m := LINE.match(line):
            name = m.group(1)
            lines.append(f"{name}={values.get(name, '')}")
            done.add(name)
        else:
            lines.append(line)
    extra = [f"{k}={v}" for k, v in values.items() if k not in done]
    if extra:
        lines += ["", *extra]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def hidden(value: str) -> str:
    """How a key is shown: never any of it (screens get recorded)."""
    return f"set ({len(value)} characters)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ask", action="store_true", help="ask for every key again")
    args = parser.parse_args()

    values = read(ENV)
    changed = not ENV.exists()
    for name, (required, what, where) in KEYS.items():
        current = values.get(name, "")
        if current and not args.ask:
            print(f"  {name}: {hidden(current)}")
            continue
        if name in values and not required and not args.ask:   # skipped before: not asked every start
            print(f"  {name}: not set (optional; start.bat keys to add it)")
            continue
        print(f"\n  {name}{'' if required else ' (optional)'}: {what}")
        print(f"  Get it at {where}")
        keep = " Enter keeps the current one." if current else (" Enter skips it." if not required else "")
        try:
            typed = getpass.getpass(f"  Paste it (it won't show).{keep} > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            typed = ""
        if typed:
            values[name] = typed
            changed = True
            print(f"  {name}: {hidden(typed)}")
        elif not current:
            values.setdefault(name, "")
    if changed:
        write(values)
        print(f"\n  Saved in {ENV.name} (git-ignored: it stays on this machine).")
    missing = [n for n, (required, _, _) in KEYS.items() if required and not values.get(n)]
    if missing:
        print(f"\n  Missing: {', '.join(missing)}. The app will open, but making an ad needs it: "
              f"run start.bat keys to add it.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
