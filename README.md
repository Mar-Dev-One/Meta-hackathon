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
  | `camera.get` / `camera.set` | Creates or moves a Camera entity, aims it at a point once and makes it the one the frame is seen through |
  | `product.create` | A product spun from a profile: a template (`perfume`, `bottle`, `jar`, `can`, `dropper`) or your own parts, colours as `"#RRGGBB"`, and an optional label image wrapped round its body |
  | `backdrop.create` | A cyclorama (a floor curving up into a wall) or a round pedestal, optionally covered with an image |
  | `lighting.preset` | A lighting setup around a subject: `three_point`, `rim_dark`, `high_key`, `top_soft`, `split`, `neon_dual`; its lights are `light_*` entities |
  | `camera.move` | A shot's camera move around a subject: `static`, `orbit`, `dolly`, `crane`, `truck`, `reveal` or `zoom`, framed so the subject fills a share of the frame. Written as timeline keys; moves placed end to end are cuts |
  | `timeline.set_track` / `timeline.add_key` | Keyframes any number, vec3 or colour field of any component (`Transform.position`, `Camera.fov_degrees`, `Light.intensity`, `MeshRenderer.material.roughness`, ...) with easing: linear, in, out, in_out, step or a cubic bezier |
  | `timeline.remove_track` / `timeline.clear` / `timeline.get` | Edit and read the tracks |
  | `timeline.seek` | Shows the scene at a time: every animated field set to its value then |
  | `timeline.play` / `timeline.pause` | Plays the timeline in real time in the window |
  | `shot.preview` | Renders the frames at given times as PNGs, through the active camera, and returns their paths |
  | `shot.render` | Renders a time range at an fps straight into an `.mp4` (`video`; needs ffmpeg on the PATH) or as PNG frames (`out_dir`) |
  | `shot.bounds` | Where an entity is in the frame at a time: its box, centre, how much of the frame it fills, which edges cut it |

A failed command changes nothing and says which argument is wrong and what it accepts. Every change is also pushed to all clients as a `scene.changed` notification.

Products and backdrops are written as glTF files under the project's `products/` folder (`<exe>/assets/products`) and loaded by the engine like any model, so scenes that use them reload after a restart. A file's name carries a hash of what it was made from: the same request reuses it.

The Studio's own state (the timeline, the active camera and what it looks at, the render settings) is saved and loaded with the scene (`scene.save` / `scene.load`), as `scenes/<name>.studio.json` next to the scene file. A track names its entity, so it keeps working through undo and scene loads.

`camera.move` keeps the camera aimed at a target entity (`camera_target`) whose position is keyframed too, so every move is position, aim and lens keys over its own time range:

```json
-> {"jsonrpc": "2.0", "id": 3, "method": "camera.move", "params": {"move": "orbit", "subject": "product",
    "start": 0, "duration": 4, "azimuth": -40, "to_azimuth": 40, "elevation": 8, "fill": 0.6}}
```

```json
-> {"jsonrpc": "2.0", "id": 2, "method": "timeline.set_track", "params": {"entity": "camera", "component": "Transform",
    "field": "position", "keys": [{"t": 0, "value": [0, 1, 4], "ease": "in_out"}, {"t": 4, "value": [3, 1, 3]}]}}
```

Shots render offscreen at any size, independent of the window, with their own renderer. Each frame is rendered from scratch at its time (the timeline evaluated there, TAA restarted, then `samples` sub-frames), so a frame looks the same whether it's rendered alone or in a sequence: the critic can re-check one frame. Defaults: previews 960x540 with 8 samples, renders 1920x1080 with 16 samples at 30 fps. On an Intel Iris Xe, a 1080p frame takes about 0.4 s into a video; PNGs are slower (about 1.2 s at 1080p, mostly compression), so use them for previews.

A render blocks the Studio until it's done, and the server doesn't answer WebSocket pings meanwhile: clients should turn off their ping timeout (`websockets.connect(url, ping_interval=None)` in Python) or render in shorter ranges.

## Pipeline (Python)

```
.venv\Scripts\python -m pip install -r pipeline\requirements.txt
.venv\Scripts\python -m pipeline.demos.ads --list          # the hand-made ads
.venv\Scripts\python -m pipeline.demos.ads --preview       # a few frames of each as PNGs
.venv\Scripts\python -m pipeline.demos.ads fizzo kora      # pipeline/demos/out/<name>.mp4 (no names: all of them)
```

- `pipeline/studio`: `Studio`, an async client that starts `Studio.exe --hidden`, connects through `server.json` and turns failed commands into `StudioError`s.
- `pipeline/encode`: `finish()`, the last ffmpeg pass: titles faded over the picture, fades from and to black.
- `pipeline/demos/ads.py`: five ads written by hand as specs (scene, product, label, lighting, shots, titles) for fictional brands: a perfume, a drinks can, a skincare jar, an olive oil, a serum. Test footage, fallback demos, and the shape of what the director agent will write. `first_ad.py` renders the perfume one.
- `pipeline/meta/smoke`: one test call to each Meta model.

## Tests

```
ctest --test-dir build -C Release
```

runs the timeline's tests (`Engine/tests/timeline_tests.c`: easing, sampling, editing, writing into a World, JSON). They need no window or GPU.

## Layout

- `src/main.c` is the Studio program
- `Engine/` is `Meta_Engine`, the library written for this project on top of the engine: `src/Studio` (studio commands), `src/Timeline` (keyframe animation), `src/Shot` (frames, video), `src/Products` (product and backdrop models as glTF), `src/Common` (JSON helpers), `tests/`; text to come
- `pipeline/` is the Python side: the Studio client, finishing with ffmpeg, demos, the Meta model smoke tests
- `Deps/` holds the engine headers (`Includes/PBR`) and prebuilt libraries (`Libs`)
- `Assets/Shaders/shaders` holds the engine's shaders. They are copied to `<exe>/assets/shaders` at build time
- `Assets/models` and `Assets/hdri` hold the models and HDRI the demo scene loads. They are copied to `<exe>/assets` at build time
- `docs/ROADMAP.md` is the plan

At runtime the program loads everything from the `assets/` folder next to it. `PBR_Engine.lib` was built with no absolute paths, so nothing outside the build folder is used. You can copy `build/Release` to another machine and run it there. The build also copies `vcruntime140.dll` next to the exe, so a Windows 10/11 PC without Visual Studio or the Visual C++ Redistributable can run it. It only needs an OpenGL 4.x graphics driver.

## Built during the hackathon

The engine (`PBR_Engine`, [AI-Powered-PBR-Renderer](https://github.com/Mar-Dev-One/AI-Powered-PBR-Renderer)) existed before the hackathon and is used unchanged, as a prebuilt library. Everything in this repository was written during the hackathon (from 2026-10-27):

- `Engine/`: the Studio library (`Meta_Engine`): studio commands, the timeline and its tests, shot rendering to PNG and video, camera moves, lighting presets, product and backdrop models
- `src/main.c`: the Studio program
- `pipeline/`: the Studio client, the ffmpeg finishing pass, the hand-made ads, the Meta model smoke tests
