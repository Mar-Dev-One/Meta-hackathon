"""The Windows release: one zip a judge can run without Visual Studio. The
repository as committed (git archive HEAD: no .env, runs or cache), plus the
built Studio in build/Release, laid out as the build lays it out (CMakeLists.txt:
the exe, vcruntime140.dll, engine/shaders, assets/models, /hdri, /fonts), so
start.bat finds Studio.exe and skips the build. Written to dist/.

    python scripts/release.py                  # dist/Studio-<commit>-windows-x64.zip
    python scripts/release.py --name submission
"""

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILT = ROOT / "build" / "Release"
DIST = ROOT / "dist"

# what the build puts next to Studio.exe (CMakeLists.txt), from where it comes; the build
# folder's own assets/ also caches what runs download, which stays out
STUDIO = [("Studio.exe", BUILT / "Studio.exe"),
          ("vcruntime140.dll", BUILT / "vcruntime140.dll"),
          ("engine/shaders", ROOT / "Assets" / "Shaders" / "shaders"),
          ("assets/models", ROOT / "Assets" / "models"),
          ("assets/hdri", ROOT / "Assets" / "hdri"),
          ("assets/fonts", ROOT / "Assets" / "fonts")]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="the zip's version (default: the commit)")
    args = parser.parse_args()

    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Uncommitted changes: the release is HEAD, so commit them first.")
    if not (BUILT / "Studio.exe").exists():
        sys.exit("No build/Release/Studio.exe: build the Studio first (start.bat setup).")
    built = (BUILT / "Studio.exe").stat().st_mtime
    changed = int(git("log", "-1", "--format=%ct", "--", "Engine", "Studio", "CMakeLists.txt", "Deps"))
    if built < changed:
        sys.exit("build/Release/Studio.exe is older than the last change to the Studio's code: build it again.")

    version = args.name or git("rev-parse", "--short", "HEAD")
    top = f"Studio-{version}"
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{top}-windows-x64.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--prefix={top}/", "-o", str(out), "HEAD"], cwd=ROOT, check=True)

    added = 0
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as z:
        for name, source in STUDIO:
            if not source.exists():
                if name == "vcruntime140.dll":   # not every Build Tools has it: the PC then needs the Redistributable
                    print("  no vcruntime140.dll next to Studio.exe: the release needs the VC++ Redistributable")
                    continue
                sys.exit(f"Missing {source}")
            files = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
            for f in files:
                inside = name if source.is_file() else f"{name}/{f.relative_to(source).as_posix()}"
                z.write(f, f"{top}/build/Release/{inside}")
                added += 1
    print(f"{out} ({out.stat().st_size / 1e6:.0f} MB; HEAD {git('rev-parse', '--short', 'HEAD')} "
          f"and {added} built files)")


if __name__ == "__main__":
    main()
