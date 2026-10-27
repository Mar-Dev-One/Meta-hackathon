# Meta-hackathon

The Studio: a renderer that AI agents drive over a command server to build and shoot 3D product scenes, on top of the prebuilt `PBR_Engine` library. See [docs/ROADMAP.md](docs/ROADMAP.md) for where it is heading: brief and product photos in, a finished marketing video out.

## Build

Requires Windows, Visual Studio 2022 (MSVC) and CMake 3.26+. The engine libraries in `Deps/Libs` are MSVC Release builds, so every configuration links the release C runtime (`/MD`). A Debug build is your code unoptimized with symbols. The engine itself stays optimized.

```
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
build\Release\Studio.exe
```

The Studio starts on an empty stage. Options:

- `--demo-scene` starts with the demo scene (a material grid and Suzanne on a pedestal) instead.
- `--hidden` runs without a visible window. The command server still runs, so the agents can use it as their renderer.
- `--width W --height H` sets the window's and frame's size in pixels (default 1600x900).
- `--check out.png` renders the demo scene in a hidden window, saves it and exits (0 on success).
- `--view NAME` shows a debug view (albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe, lights).

## Command server

The Studio runs a command server that other programs use to build the scene. It is a WebSocket server on `127.0.0.1` that speaks JSON-RPC 2.0. The default port is 7468; `--port N` picks another, and if the port is taken it uses any free one. It doesn't run with `--check`.

When the server starts, it writes `server.json` next to the exe with the URL to connect to. The URL includes a token that changes every run. The file is deleted when the Studio closes normally.

```json
{"url": "ws://127.0.0.1:7468/?token=...", "port": 7468, "token": "...", "pid": 1234}
```

The method is the command name and the params are its arguments:

```json
-> {"jsonrpc": "2.0", "id": 1, "method": "camera.set", "params": {"position": [3, 2, 3], "target": [0, 0.5, 0]}}
<- {"jsonrpc": "2.0", "id": 1, "result": {"camera": "camera", "position": [3, 2, 3], "rotation_deg": [-19.47, 45, 0], ...}}
```

`commands.list` describes every command and its arguments. There are two sets:

- **The engine's:** `entity.create`, `entity.place`, `component.set`, `scene.save`, `history.undo`, ... (`Deps/Includes/PBR/Commands/Commands.h`).
- **The Studio's** (`Engine/src/Studio/Studio.h`):

  | Command | What it does |
  |---|---|
  | `studio.reset` | Empties the stage: every entity destroyed, environment, render settings and active camera reset |
  | `environment.get` / `environment.set` | HDRI, image-based lighting, exposure, bloom, tone mapping, SSAO |
  | `render.get` / `render.set` | Antialiasing, shadows, background colour |
  | `camera.get` / `camera.set` | Creates or moves a Camera entity, aims it at a target and makes it the one the frame is seen through |

A failed command changes nothing and says which argument is wrong and what it accepts. Every change is also pushed to all clients as a `scene.changed` notification.

## Layout

- `src/main.c` is the Studio program
- `Engine/` is `Meta_Engine`, the library written for this project on top of the engine (studio commands; timeline, text, products and shot rendering to come)
- `Deps/` holds the engine headers (`Includes/PBR`) and prebuilt libraries (`Libs`)
- `Assets/Shaders/shaders` holds the engine's shaders. They are copied to `<exe>/assets/shaders` at build time
- `Assets/models` and `Assets/hdri` hold the models and HDRI the demo scene loads. They are copied to `<exe>/assets` at build time
- `docs/ROADMAP.md` is the plan

At runtime the program loads everything from the `assets/` folder next to it. `PBR_Engine.lib` was built with no absolute paths, so nothing outside the build folder is used. You can copy `build/Release` to another machine and run it there. The build also copies `vcruntime140.dll` next to the exe, so a Windows 10/11 PC without Visual Studio or the Visual C++ Redistributable can run it. It only needs an OpenGL 4.x graphics driver.

## Built during the hackathon

The engine (`PBR_Engine`, [AI-Powered-PBR-Renderer](https://github.com/Mar-Dev-One/AI-Powered-PBR-Renderer)) existed before the hackathon and is used unchanged, as a prebuilt library. Everything in this repository was written during the hackathon (from 2026-10-27):

- `Engine/`: the Studio library (`Meta_Engine`)
- `src/main.c`: the Studio program
