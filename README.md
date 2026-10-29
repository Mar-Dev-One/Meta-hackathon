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
  | `product.create` | A product spun from a profile: a template (`perfume`, `bottle`, `jar`, `can`, `dropper`) or your own parts, colours as `"#RRGGBB"`, and an optional label image wrapped round its body. A part can be glass (`transmission`, `ior`, `thickness`, `attenuation_color` / `attenuation_distance`: it shows the set behind it, bent and tinted), clear-coated (`clearcoat`) or have its own `specular`; they're written into the product's glTF as the `KHR_materials_*` extensions |
  | `backdrop.create` | A cyclorama (a floor curving up into a wall) or a round pedestal, optionally covered with an image |
  | `lighting.preset` | A lighting setup around a subject: `three_point`, `rim_dark`, `high_key`, `top_soft`, `split`, `neon_dual`; its lights are `light_*` entities. `glow` adds a soft pool of light on the backdrop's wall behind the product, so glass lights up in its liquid's colour (a backlit bottle) |
  | `camera.move` | A shot's camera move around a subject: `static`, `orbit`, `dolly`, `crane`, `truck`, `reveal` or `zoom`, framed so the subject fills a share of the frame, and with an `aperture`, a shallow focus that keeps the subject's front sharp while what's behind softens. Written as timeline keys (position, aim, lens, focus, aperture); moves placed end to end are cuts |
  | `timeline.set_track` / `timeline.add_key` | Keyframes any number, vec3 or colour field of any component (`Transform.position`, `Camera.fov_degrees`, `Light.intensity`, `MeshRenderer.material.roughness`, ...) with easing: linear, in, out, in_out, step or a cubic bezier |
  | `timeline.remove_track` / `timeline.clear` / `timeline.get` | Edit and read the tracks |
  | `timeline.seek` | Shows the scene at a time: every animated field set to its value then |
  | `timeline.play` / `timeline.pause` | Plays the timeline in real time in the window |
  | `text.create` / `text.set` / `text.remove` / `text.get` / `text.measure` | Titles drawn over the picture in the window and every shot frame: font (`serif`, `sans`, `sans_bold`, `condensed`, `script`), size as a share of the frame's height, anchor and offset, colour `"#RRGGBB(AA)"`, letter and line spacing; saved with the scene. Animate them on the timeline as component `"Text"` (the title's name as the entity): `opacity`, `offset`, `scale`, `tracking`, `size`, `color`. `text.measure` gives a title's box at any frame size, and whether it fits, without adding it |
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
.venv\Scripts\python -m pipeline.runs                     # the runs; `last` shows the newest, `--replay 20` replays it 20x faster
.venv\Scripts\python -m pipeline.agents.analyst Assets\photos\mira_jar.png --category "cream jar" --video   # brand profile, contact sheet, turntable
.venv\Scripts\python -m pipeline.agents.director.write --video   # three test briefs: storyboards and videos (after the analyst)
.venv\Scripts\python -m pipeline.agents.producer Assets\photos\aurelle_perfume.png "Luxury perfume ad, dark and moody, 15 seconds." --category "perfume bottle"   # photo + brief -> ad
```

- `pipeline/studio`: `Studio`, an async client that starts `Studio.exe --hidden`, connects through `server.json` and turns failed commands into `StudioError`s; and `build(studio, storyboard)`, which turns a storyboard into Studio commands (scene, product, lights, camera moves, titles, extra tracks) and returns its length. `render.py` takes a built storyboard out of the Studio into a run: `preview()` (frames from the middle of each shot and the end) and `render()` (the video, sized to the storyboard's frame: 16:9, 9:16 or 1:1, faded in and out).
- `pipeline/schemas`: the pipeline's data as pydantic models: `Storyboard` (an ad: look, product, shots, titles), `BrandProfile` (what the brand analyst reads from photos), `Critique` (the critic's scores and fixes). Their field descriptions are written for the model that fills them; `python -m pipeline.schemas.export` writes their JSON Schemas to `pipeline/schemas/json`.
- `pipeline/encode`: `finish()`, the last ffmpeg pass: the whole ad faded from and to black (titles are drawn by the Studio).
- `pipeline/demos/ads.py`: five ads written by hand as `Storyboard`s for fictional brands: a perfume, a drinks can, a skincare jar, an olive oil, a serum. Test footage, fallback demos, and examples of what the director agent writes (`--export` writes them as JSON). `first_ad.py` renders the perfume one. Each ad is made inside a run folder.
- `pipeline/runs.py`: run folders, `runs/<date>-<time>-<slug>/` (git-ignored): the inputs, `storyboard.json`, preview `frames/`, `final/<name>.mp4`, a `run.json` summary (status, time, model cost, outputs) and `log.jsonl`, every event with its time: each Studio command with its arguments, each model call with its cost, files saved, and the error if the run failed. `python -m pipeline.runs` lists runs, shows one, or replays it with its timing.
- `pipeline/meta`: the Meta models as the agents call them: `spark.ask()` (text, images, answers checked against a JSON schema or pydantic model; `provider="baseten"` for Muse Spark Open), `spark.run_tools()` (tool calling), `sam.segment()` (full-size masks), `image.generate()`, `voice.transcribe()`. Every call is cached on disk by its request in `cache/meta` (SAM's decoded masks too: decoding takes seconds) (git-ignored; rerunning costs nothing; `META_CACHE=off` to bypass), retried on rate limits and server errors, and recorded in `usage` with its tokens and cost. Failures raise `MetaError` with the server's message.
- `pipeline/agents/analyst`: the brand analyst, a product photo in, a `BrandProfile` out (`analyse(run, photo, category)`; `profile.product()` is a storyboard's product). `segment.py` finds the product with SAM 3.1 (the largest match of its category) and its cap and label, keeping only matches on the product, cut to its mask. `palette.py` finds the colours with k-means in Lab, part by part, one per colour family so light and shade don't count as colours: product, accent, label, text. `materials.py` asks Muse Spark, shown the photo, the masks and the palette, for what pixels can't say: the brand name, the real height, each part's material (colour, metallic, roughness; glass as transmission with the colour of what it holds; a clear coat), the typography, the mood and what an advert must avoid, checked against a schema. `profile.py` turns the product's mask into its 3D shape: the half-width of each row about the vertical axis, median-filtered, simplified to a few points, scaled to the height and split into body and cap. `label.py` cuts the label out and unrolls it from the body's curve (the inverse of the Studio's wrap), dividing out the photo's shading; a label that reaches both sides of the silhouette goes all the way round. Each run keeps the photo, `masks.png`, `outline.png`, `label.png`, `brand_profile.json`, a turntable and `contact_sheet.png` (masks, profile, turntable frames, label, palette, what Spark read).
- `pipeline/agents/director`: the director (in progress). `grammar.md` is the shot grammar for its prompt: the camera moves and what each reads, the lights, the set, titles, tracks, ad-craft rules and the styles, written by `python -m pipeline.agents.director.grammar` from the Studio's `commands.list` and the Storyboard schema, after checking that every name the schema allows is one the Studio knows. `styles.py` is the style library: 8 looks to start from (luxury_dark, clean_minimal, bold_energetic, natural_organic, warm_glow, tech_sleek, playful_pop, soft_pastel), each a whole `Look` with its title type, pacing, moves and depth of field (an aperture); `python -m pipeline.agents.director.styles` renders a sample of each. `write.py` turns a brief and a brand profile into a storyboard: Muse Spark writes a plan (the storyboard without the product, which is the profile's) from the brief, the profile, the style library and the grammar; it's validated, then checked in code (lengths add up, consecutive shots move differently, the last shot is a still front hero with the brand's name, the pedestal in proportion with the product, titles placed off the product, fit the frame as the Studio measures them, and don't overlap). What's wrong goes back to Spark with its answer, up to 3 tries. `python -m pipeline.agents.director.write` writes storyboards for three test briefs (`--preview`, `--video` to render them in the same run). `revise.py` changes a storyboard to answer a written fix (the critic's or a person's): Muse Spark calls tools that edit the storyboard (`edit_shot`, `add_shot`, `remove_shot`, `edit_look`, `edit_title`, `add_title`, `remove_title`), each checked against the schema as it's made, the craft rules when it's done; it returns the revised storyboard and exactly what changed. The tools edit the storyboard, not the Studio, so every revision can be rebuilt, compared and undone.
- `pipeline/agents/producer.py`: the whole chain, `make_ad(studio, run, brief, photo)`: the brand analyst reads the photo, the director plans the ad, the Studio builds it, previews a few frames and renders the video, all in one run folder (`brand_profile.json`, masks, label, `storyboard.json`, `frames/`, `final/<photo>.mp4`, and the log of every model call and Studio command).
- `pipeline/meta/smoke`: one test call to each model through those clients (`run_all.py`, `--fresh` to skip the cache).

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
- `Assets/Shaders/shaders` holds the engine's shaders. They are copied to `<exe>/engine/shaders` at build time
- `Assets/photos` holds product photos of fictional brands for testing the brand analyst, made with Muse Image by `scripts/sample_photos.py`
- `Assets/models` and `Assets/hdri` hold the models and HDRI the demo scene loads. They are copied to `<exe>/assets` at build time
- `docs/ROADMAP.md` is the plan

At runtime the program loads the engine's shaders from the `engine/` folder next to it and everything else from the `assets/` folder next to it, so nothing outside the build folder is used (the engine looks in `<exe>/engine` before its own source tree). You can copy `build/Release` to another machine and run it there. The build also copies `vcruntime140.dll` next to the exe, so a Windows 10/11 PC without Visual Studio or the Visual C++ Redistributable can run it. It only needs an OpenGL 4.x graphics driver.

## Built during the hackathon

The engine (`PBR_Engine`, [AI-Powered-PBR-Renderer](https://github.com/Mar-Dev-One/AI-Powered-PBR-Renderer)) existed before the hackathon and is used as a prebuilt library. During the hackathon four rendering features were added to it, on its `features/glass-and-focus` branch: glass (transmission, index of refraction, thickness, absorption), depth of field (the camera's focus distance and aperture), clearcoat and specular. Everything else the engine does (PBR, image-based lighting, shadows, bloom, TAA, SSAO, the world and its commands) predates the hackathon. Everything in this repository was written during the hackathon (from 2026-10-27):

- `Engine/`: the Studio library (`Meta_Engine`): studio commands, the timeline and its tests, shot rendering to PNG and video, camera moves, lighting presets, product and backdrop models
- `src/main.c`: the Studio program
- `pipeline/`: the Studio client, the ffmpeg finishing pass, the hand-made ads, the Meta model clients and their smoke tests, the schemas, run folders, the brand analyst
- `Assets/photos`: the test product photos (generated with Muse Image)
