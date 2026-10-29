# Studio: a product photo and a brief in, a finished 3D ad out

Give it one photo of a product and a sentence like *"Luxury perfume ad, dark and moody, 15 seconds"*. A team of AI agents reads the brand from the photo, rebuilds the product in 3D, plans the shots, renders them in a real-time PBR renderer, and then **checks its own work frame by frame**, revising until the ad passes. You get a finished MP4 in 16:9 and 9:16, with titles and music.

Built for the **Meta Global AI Developer Hackathon** (October 27 to November 4, 2026) on Meta's models: Muse Spark, **Muse Spark Open** (the critic runs on it by default) and SAM 3.1.

## How it works

```
 product photo + brief
        │
        ▼
 ┌──────────────┐  brand profile   ┌──────────────┐  storyboard   ┌─────────────────────┐
 │ Brand analyst│ ───────────────► │   Director   │ ────────────► │  Studio (renderer)  │
 │ SAM 3.1      │  3D shape,       │ Muse Spark   │               │  C, JSON-RPC over   │
 │ Muse Spark   │  materials,      │ (tools)      │ ◄──── fixes ─ │  WebSocket          │
 └──────────────┘  palette, label  └──────────────┘        │      └──────────┬──────────┘
                                                            │                 │ frames
                                                     ┌──────┴───────┐         │
                                                     │    Critic    │ ◄───────┘
                                                     │ measurements │
                                                     │ + Muse Spark │
                                                     │   Open vision│
                                                     └──────┬───────┘
                                                            │ every shot and the whole ad pass
                                                            ▼
                                        final cut: 16:9 and 9:16, titles, music (MP4)
```

1. **Brand analyst** (photo → brand profile). SAM 3.1 segments the product, its cap and its label. The product's silhouette becomes a 3D shape spun around its axis, and the label is cut from the photo and unrolled from the curve. The palette comes from k-means in Lab colour space. Muse Spark reads what pixels can't: the brand name, each part's material (glass, metal, matte plastic), the typography, the mood, and what an ad for this brand must avoid.
2. **Director** (brief + profile → storyboard). Muse Spark plans the ad as data: the look (set, lights, environment), the shots (one camera move each: orbit, dolly, crane, truck, reveal, zoom), titles and animation. Code checks the craft rules (lengths add up, consecutive shots move differently, the ending is a hero shot with the brand's name, titles fit the frame and stay off the product) and sends problems back to the model.
3. **Studio** (storyboard → frames). The C renderer builds the set and the product as glTF, keys every camera move on a timeline, draws titles with signed-distance-field fonts, and renders deterministic frames offscreen at any size.
4. **Critic loop** (frames → scores and fixes). Each shot is measured, then judged against a rubric. The cuts and the whole ad are judged too. Failing issues go back to the director as storyboard edits, the ad is rebuilt and judged again: at most 3 revisions, and the best round is kept. See [The critic](#the-critic).
5. **Final cut.** The ad is rendered horizontal (16:9), vertical (9:16), or both from the same storyboard, as you choose. For a second frame, titles are refitted, and a squat product is framed by the frame's width. It gets music in the style's mood, cut to length and landing on the hero shot, and is encoded as H.264 and AAC.

Every run is a folder (`runs/<time>-<name>/`) holding every input, output, frame, critique and a timed log of each model call and renderer command. A run can be replayed in the app at its real pace, for demos.

## The critic

The critic is what makes the output trustworthy. It **measures first and judges second**:

- **Measured, exact.** The Studio renders each frame three ways: as is, with the product's shadow off, and without the product. The difference gives the product's exact pixels. From them it measures:
  - how much of the frame the product fills, and which edges cut it;
  - how much of its outline merges with the background (a missing rim light);
  - highlights blown to white and shadows crushed to black;
  - how far the rendered colours are from the brand's;
  - whether a title sits over the product.

  At every cut it reads, from the Studio itself, how far the camera turns around the product and whether the set's lights change.
- **Judged, by vision.** Muse Spark Open sees each shot's frames with those numbers, the brief and the brand, and scores composition, lighting, product visibility, brand, continuity and titles from 0 to 10, against written anchors. A second pass judges the whole ad: pacing, continuity across cuts, the arc, the brand.
- **Bound by the measurements.** A major measured fault must appear in the critique, with that category scored 6 or less, or the answer goes back to the model.
- **Fair to intent.** A reveal from darkness, lights fading up, and a close-up that crops on purpose are named in the prompt and exempt from the measured checks, so they aren't judged as faults.
- **Steady near the pass mark.** A shot passes when every score is 7 or more and no major issue remains, decided in code. When the lowest score is 6 or 7, the shot is judged a second time and the worse result is kept.

The critic's fixes are written in storyboard terms (`shots[1].camera.fill 0.9 -> 0.65`, `remove tracks[1]`). The director applies them through tools that edit the storyboard, checked against the schema as they're made.

### Results so far

- **A broken ad fixed by the loop.** The lights were cut to a fifth and one shot slid the product out of frame. It went from **1 of 5 shots passing to 5 of 5** in three revisions, with no human input.
- **A broken cut caught and fixed.** A cut swung to the back of the can while the light changed colour. The whole-ad pass flagged it, scoring continuity 3, and **one revision** fixed it (continuity 8, every shot and the ad passing).
- **Muse Spark Open vs Muse Spark as the critic.** 19 shots from five ads, each judged twice by each model:

  | | Muse Spark | Muse Spark Open |
  |---|---|---|
  | Same pass/fail when a shot is judged twice | 89% | 84% |
  | Time per critique | 35 s | 37 s |
  | Answers that broke the schema | 0 | 0 |

  The two agree on pass/fail for 74% of shots, and every disagreement is near the pass mark. The critic runs on Muse Spark Open by default: it's as fast as Muse Spark, nearly as consistent, and has open weights.
- **Known limit:** a white product on a bright set in a vertical frame doesn't yet reach a full pass within three revisions. The loop keeps its best round.

A full ad (analysis, storyboard, critic loop, two 1080p videos) takes about 20–25 minutes on a laptop's integrated GPU (Intel Iris Xe). It costs about $0.20 on the Meta Model API, plus the Muse Spark Open calls on Baseten. Every model answer is cached on disk, so a rerun costs nothing.

## Meta models

| Model | Used for |
|---|---|
| **Muse Spark** | Reading the brand from the photo (vision, JSON answers); writing storyboards; revising them with tool calls |
| **Muse Spark Open** (Baseten) | The critic, by default: per-shot and whole-ad judgment from rendered frames |
| **SAM 3.1** | Segmenting the product, cap and label: its silhouette becomes the 3D shape, its label the texture |
| **Muse Image** | The test product photos of fictional brands (`Assets/photos`) |

## Quick start

**Requirements:** Windows 10 or 11, an OpenGL 4.x GPU, Visual Studio 2022 (MSVC), CMake 3.26+, Python 3.11+ (developed on 3.13), and ffmpeg on the `PATH`.

**API keys:** copy `.env.example` to `.env` and fill in `MODEL_API_KEY` (Meta Model API, [dev.meta.ai](https://dev.meta.ai)) and `BASETEN_API_KEY` (Muse Spark Open). `.env` is git-ignored.

```bat
:: The renderer
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release

:: The pipeline
python -m venv .venv
.venv\Scripts\python -m pip install -r pipeline\requirements.txt

:: The app: http://127.0.0.1:8000
.venv\Scripts\python -m app
```

In the app, drop a product photo, write a brief, choose the format (horizontal 16:9, vertical 9:16, or both) and press **Make the ad**. The page fills in as the agents work: the brand profile, the storyboard, a table of critic scores round by round (click a cell for its issues and fixes), and the videos. Any past run can be opened, or replayed at its real pace.

From the command line:

```bat
:: A photo and a brief in, an ad out (in runs\); --format horizontal, vertical or both (the default)
.venv\Scripts\python -m pipeline.agents.producer Assets\photos\aurelle_perfume.png "Luxury perfume ad, dark and moody, 15 seconds." --category "perfume bottle" --format horizontal

:: Five ads written by hand as storyboards (test footage and examples)
.venv\Scripts\python -m pipeline.demos.ads fizzo kora --vertical

:: The critic on those ads: measure, judge, or run the whole loop
.venv\Scripts\python -m pipeline.agents.critic kora --judge
.venv\Scripts\python -m pipeline.agents.critic fizzo --refine --broken

:: Muse Spark vs Muse Spark Open as the critic
.venv\Scripts\python -m pipeline.agents.critic.compare

:: Runs: list, show, replay
.venv\Scripts\python -m pipeline.runs
```

The app's API: `POST /runs` (a photo, a brief and a `format`), `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (Server-Sent Events, live or replayed with `?speed=1`) and `GET /runs/{id}/files/{path}`.

## The Studio

`build\Release\Studio.exe` is the renderer the agents drive. It starts on an empty stage. Options:

- `--hidden` runs without a window. The command server still runs; this is how the pipeline uses it.
- `--demo-scene` starts with a material grid and Suzanne instead of an empty stage.
- `--width W --height H` sets the window's size (default 1600×900).
- `--check out.png` renders the demo scene, saves it and exits (0 on success).
- `--view NAME` shows a debug view: albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe or lights.

It serves **JSON-RPC 2.0 over WebSocket** on `127.0.0.1:7468` (`--port N` for another), and writes the URL with a per-run token to `server.json` next to the exe. The method is the command and the params are its arguments:

```json
-> {"jsonrpc": "2.0", "id": 1, "method": "camera.move", "params": {"move": "orbit", "subject": "product",
    "start": 0, "duration": 4, "azimuth": -40, "to_azimuth": 40, "elevation": 8, "fill": 0.6}}
```

`commands.list` describes every command and its arguments. A failed command changes nothing and says which argument is wrong and what it accepts.

<details>
<summary>The Studio's commands</summary>

| Command | What it does |
|---|---|
| `studio.reset` | Empties the stage: every entity destroyed; the environment, render settings and active camera reset |
| `environment.get` / `environment.set` | HDRI, image-based lighting, exposure, bloom, tone mapping, SSAO |
| `render.get` / `render.set` | Antialiasing, shadows, background colour |
| `camera.get` / `camera.set` | Creates or moves a camera and makes it the one the frame is seen through |
| `product.create` | A product spun from a profile: a template (`perfume`, `bottle`, `jar`, `can`, `dropper`) or your own parts, with colours and an optional label image wrapped round its body. A part can be glass (transmission, index of refraction, thickness, the colour of what it holds), clear-coated, or have its own specular |
| `backdrop.create` | A cyclorama (a floor curving up into a wall) or a round pedestal, optionally covered with an image |
| `lighting.preset` | A lighting setup around a subject: `three_point`, `rim_dark`, `high_key`, `top_soft`, `split`, `neon_dual`; `glow` adds a pool of light behind it, so glass lights up in its liquid's colour |
| `camera.move` | A shot's camera move around a subject: `static`, `orbit`, `dolly`, `crane`, `truck`, `reveal` or `zoom`. `fill` is the subject's share of the frame's height, as seen from the camera's elevation, so a jar and a bottle frame alike. `aperture` sets a shallow focus that keeps the subject sharp. Moves placed end to end are cuts |
| `timeline.set_track` / `add_key` / `remove_track` / `clear` / `get` | Keyframes any number, vector or colour field of any component, with easing (linear, in, out, in_out, step, cubic bezier) |
| `timeline.seek` / `play` / `pause` | The scene at a time; real-time playback in the window |
| `text.create` / `set` / `remove` / `get` / `measure` | Titles drawn over every frame: five open-licensed fonts, size as a share of the frame's height, anchor, colour, letter spacing. Their opacity, offset, scale and tracking can be animated |
| `shot.preview` | Renders the frames at given times as PNGs |
| `shot.render` | Renders a time range straight into an `.mp4` (through ffmpeg) or as PNG frames |
| `shot.bounds` | Where an entity is in the frame at a time: its box, centre, share of the frame, and which edges cut it |

Plus the engine's own commands: `entity.create`, `component.set`, `scene.save`, `history.undo`, and more.

Frames render offscreen at any size, each from scratch at its time, so a frame looks the same alone or in a sequence and the critic can re-check any one. On an Intel Iris Xe a 1080p frame takes about 0.4 s into a video. A render blocks the Studio, so clients should turn off WebSocket ping timeouts.

</details>

## Repository layout

```
src/main.c                  the Studio program
Engine/                     Meta_Engine, the Studio library (C): studio commands, timeline, camera moves and
                            framing, lighting presets, products and backdrops (glTF), titles (SDF fonts),
                            offscreen shot rendering; tests/
pipeline/
  meta/                     clients for the Meta models and Baseten: caching, retries, outage waits, cost tracking
  studio/                   the Studio client; storyboard → commands; rendering; reframing to 9:16
  schemas/                  pydantic models: BrandProfile, Storyboard, Critique, AdCritique
  agents/analyst/           the brand analyst
  agents/director/          the director: shot grammar, style library, writing and revising storyboards
  agents/critic/            the critic: measurements, cuts, shot and whole-ad judgment, the loop, the model comparison
  agents/producer.py        the whole chain: photo + brief → ad
  encode/                   ffmpeg finishing; the music
  demos/                    five hand-made ads for fictional brands
  runs.py                   run folders: log, outputs, replay
app/                        the web app: FastAPI backend, one HTML page
Assets/                     fonts (OFL), HDRIs (CC0), models, shaders, test product photos
Deps/                       the engine (PBR_Engine) as headers and prebuilt libraries
scripts/                    font kerning tables, the test photos
```

Tests: `ctest --test-dir build -C Release` runs the timeline's and the text layout's tests. They need no window or GPU. `pipeline/meta/smoke/run_all.py` makes one test call to each model.

## Built during the hackathon

The rendering engine (`PBR_Engine`, [AI-Powered-PBR-Renderer](https://github.com/Mar-Dev-One/AI-Powered-PBR-Renderer)) **existed before the hackathon** and is used here as a prebuilt library (`Deps/`). Its PBR shading, image-based lighting, shadows, bloom, TAA, SSAO, scene and command system all predate the event. During the hackathon, four rendering features were added to it on its `features/glass-and-focus` branch: glass (transmission, index of refraction, thickness, absorption), depth of field, clear coat and specular.

**Everything in this repository was written during the hackathon**, from 2026-10-27:

- `Engine/`: the Studio library: studio commands, the timeline and its tests, camera moves and framing, lighting presets, procedural products and backdrops, labels, titles with SDF fonts and kerning, offscreen shot rendering to PNG and video
- `src/main.c`: the Studio program and its command server setup
- `pipeline/`: every agent (brand analyst, director, critic and its loop, producer), the Meta model clients, the schemas, run folders, the final cut and its music, the hand-made ads, the model comparison
- `app/`: the web app
- `scripts/` and `Assets/photos`: the font kerning tables and the test product photos (generated with Muse Image)

## Credits and licences

- **Fonts:** Playfair Display, Montserrat, Oswald and Great Vibes, under the SIL Open Font License 1.1 (licences in `Assets/fonts`).
- **HDRIs:** from [Poly Haven](https://polyhaven.com), CC0 (`Assets/hdri/README.md`).
- **Music:** synthesized note by note by `pipeline/encode/music.py`: original, with nothing to license. A track placed at `Assets/music/<mood>.mp3` is used instead.
- **Brands:** every brand in the photos, ads and examples is fictional.
