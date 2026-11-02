# Studio: a product photo and a brief in, a finished 3D ad out

Give it one photo of a product and a brief like *"Luxury perfume ad, dark and moody, 15 seconds"*, typed or spoken. A team of AI agents reads the brand from the photo and rebuilds the product in 3D. They plan the film shot by shot, dress the set, and render it in a real-time PBR renderer. You get a finished MP4, 16:9 or 9:16, from 15 seconds to 2 minutes, with titles, an end card and music.

Built for the **Meta Global AI Developer Hackathon** (October 27 to November 4, 2026) on Meta's models: **Muse Spark**, **Muse Spark Open**, **SAM 3.1**, **Muse Image** and **Muse Voice**.

## How it works

```
 product photo + brief (typed, or spoken: Muse Voice)
        │
        ▼
 ┌───────────────┐    ┌───────────────┐    ┌──────────────┐    ┌──────────────┐
 │ Brand analyst │ ─► │ Scout + stager│ ─► │   Director   │ ─► │    Studio    │ ─► final cut
 │ SAM 3.1       │    │ + colourist   │    │  Muse Spark  │    │ C renderer,  │    16:9 / 9:16,
 │ Muse Spark    │    │ Muse Spark    │    │ + code rules │    │ JSON-RPC     │    titles, music
 └───────────────┘    └───────────────┘    └──────────────┘    └──────────────┘
  brand profile:       a 3D model when       storyboard: set,     frames, offscreen,
  palette, materials,  the product isn't     props, lights,       motion blur
  label, typography    round, stood and      shots, titles,
                       repainted             music
```

1. **Brand analyst** (photo → brand profile). SAM 3.1 finds the product, its cap and its label. Muse Spark reads what pixels can't: the brand name, each part's material (glass holding amber liquid, brushed aluminium, matte plastic), the typography, the mood, and what an ad for this brand must avoid. The palette comes from clustering in Lab colour space, skipping shade and highlights. A round product is traced from its silhouette and spun into 3D. Its label is cut from the photo, unrolled from the curve and wrapped back on. Print straight on the body, like a can's logo or an engraving, is found by colour and wrapped the same way.
2. **Scout** (photo → 3D model, for shapes that aren't round). Muse Spark decides whether the product is round. If not, it searches three free catalogues (Sketchfab, Objaverse, Poly Haven), keeping only CC0 and CC-BY models, and picks finalists from their thumbnails. Those are downloaded and rendered alike, and Spark picks the closest by its renders. **Models carrying another company's brand are refused**, whether it shows in a logo, lettering, the model's title or a specific real product. If nothing fits, the ad stops and asks for a model (`.glb`); it never guesses a shape.
3. **Stager and colourist.** Spark sees the model from several sides and says which way is up and which side faces the camera. The colourist repaints the model's own textures in the photo's colours, region by region, if Spark sees that closer to the product.
4. **Director** (brief + brand profile → storyboard). Muse Spark plans the ad as data:
   - **the set:** a style from a library of 13 looks, a surface and a light environment from Poly Haven, props at their real sizes;
   - **the film:** lights, and shots with one camera move each (orbit, dolly, crane, truck, reveal, zoom, or a free path through waypoints), product motion, titles, an end card and the music's mood and tempo.

   Code then checks the craft rules: lengths add up, consecutive shots move differently, the last shot is a hero with the brand's name, titles are readable and stay off the product, props don't float or hide it. It also checks that a coloured product isn't greyed by the tonemapper. Problems go back to Spark for the next draft; most ads need 2–3 drafts.
5. **Studio** (storyboard → frames). The C renderer builds the set and the product as glTF, keys every move on a timeline, draws titles with signed-distance-field fonts, and renders frames offscreen at any size, with a 180° shutter's motion blur.
6. **Final cut.** Shots are cut to the music's beat. The music is synthesized for the chosen mood and tempo, mastered to -16 LUFS. The end card shows the product's photo with the brand's name on a calm colour, and the film is encoded as H.264 and AAC. A second format (9:16 from a 16:9 plan) is reframed from the same storyboard.

Every run is a folder (`runs/<time>-<name>/`) holding its inputs, the brand profile, each storyboard draft, the model sheets Spark chose from, the videos, and a timed log of every model call and renderer command. A failed run also keeps its traceback. Any run can be made again from its inputs (`--again`) or replayed in the app at its real pace.

## Results

Every ad made between November 1 and 2, 2026 (72 runs), from `scripts/evaluate.py`:

| | |
|---|---|
| ads made | 61 of 72 (85%); 9 failed, 2 cancelled |
| time per ad | median 8 minutes (15 s to 2 min ads) on a laptop's integrated GPU (Intel Iris Xe) |
| Meta models per ad | median $0.165, 13 calls; answers are cached on disk, so a rerun costs nothing |
| director's drafts | 2.7 per ad on average; the next draft fixed 71% of the problems the checks found |
| product's 3D model | 39 from the catalogues (37 picked by their renders), 21 traced from the photo |

The batch behind most of these is **30 ads for 30 fictional products**, made unattended in one night (`scripts/batch_ads.py`): a candle, a drone, an espresso machine, a guitar… from 15 seconds to 2 minutes. Reviewing its frames drove the latest fixes: the logo guard, print on the body as a label, liquids that keep their colour in glass, and colours the tonemapper no longer greys.

### Known limits

- A product with no suitable free 3D model needs one uploaded; the scout won't guess its shape.
- A model stands the way the photo shows the product, not always the way it would rest: a wallet or a knife can stand on end.
- A label wraps only a round, traced body; a model keeps its own surface.
- Glass and the liquid it holds are one surface, so a bottle can look like coloured plastic.
- Long ads (1–2 minutes) vary their framing less than a human editor would.

## Meta models

| Model | Used for |
|---|---|
| **Muse Spark** (`muse-spark-1.3`) | Reading the brand from the photo; whether the product is round; picking and auditioning 3D models; standing and colouring them; writing and revising storyboards; mending a spoken brief |
| **Muse Spark Open** (Baseten) | The critic (optional): per-shot and whole-ad judgment from rendered frames |
| **SAM 3.1** | Segmenting the product, cap and label: its silhouette becomes the 3D shape, its label the texture |
| **Muse Voice** (`muse-voice-transcribe-1.0`) | The spoken brief: "Speak it" in the app |
| **Muse Image** (`muse-image-1.0`) | The product photos of fictional brands used for testing (`Assets/photos`) |

## Quick start

**Requirements:**
- Windows 10 or 11, with an OpenGL 4.x GPU.
- Visual Studio with "Desktop development with C++": any edition, or the free Build Tools. 2022 or newer is recommended; 2019 16.8 is the minimum, for C11, and may not link the engine's prebuilt libraries.
- CMake 3.26+ (Visual Studio's own is fine).
- Python 3.11+ (developed on 3.13).
- ffmpeg on the `PATH`.

**The quick way: run `start.bat`.** It checks each of these and sets up what's missing:
- **Python and ffmpeg:** offers to install them with winget.
- **The environment:** creates `.venv` and installs the packages, again whenever `pipeline\requirements.txt` changes.
- **The Studio:** builds it with CMake and Visual Studio (found with vswhere; any edition 2019 16.8+ or the Build Tools).
- **API keys:** asks for them, typed hidden, and saves them to `.env` (`scripts/setup_env.py`).

Each step acts only if something is missing, so the second run goes straight to the app. Then it starts the app on http://127.0.0.1:8000 and opens the browser; its window shows the app's log, and the Studio's window shows each shot rendering. Other modes: `start.bat keys` asks for the keys again, `start.bat setup` only sets up, and `start.bat hidden` runs without the Studio's window.

**No Visual Studio?** Download the release zip (`Studio-…-windows-x64.zip`): the Studio comes prebuilt in `build\Release`, so `start.bat` skips the build and needs only Python and ffmpeg. `scripts/release.py` makes it from the commit checked out.

**By hand.** API keys: copy `.env.example` to `.env` and fill in:
- `MODEL_API_KEY`: the Meta Model API, from [dev.meta.ai](https://dev.meta.ai).
- `BASETEN_API_KEY`: Muse Spark Open, for the critic.
- `SKETCHFAB_API_TOKEN` (optional): downloads from Sketchfab. Without it the scout uses Objaverse and Poly Haven.

`.env` is git-ignored.

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

### The app

Drop a product photo, type a brief or press **Speak it**, choose the format and press **Make the ad**. You can also search the catalogues for a 3D model, or upload your own `.glb`. The page fills in as the agents work:
- the brand profile and the 3D model with its credit;
- each storyboard draft, with what the checks found and what changed;
- **How Spark decided**: every choice in order, with the sheet it chose from;
- the videos.

A run can be cancelled or made again. Finished ads collect in the **gallery**, and any past run can be replayed at its real pace.

API: `POST /runs` (photo, brief, `format`, optional `model_pick` or `model_file`), `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (Server-Sent Events, live or replayed with `?speed=1`), `GET /runs/{id}/files/{path}`, `POST /runs/{id}/cancel`, `POST /runs/{id}/again`, `GET /gallery`, `GET /models/search?q=`, `POST /transcribe`.

### The command line

```bat
:: A photo and a brief in, an ad out (in runs\); --format horizontal, vertical or both (the default)
.venv\Scripts\python -m pipeline.agents.producer Assets\photos\aurelle_perfume.png "Luxury perfume ad, dark and moody, 15 seconds." --category "perfume bottle" --format horizontal

:: Your own 3D model (a catalogue's .glb keeps the .credit.json beside it)
.venv\Scripts\python -m pipeline.agents.producer photo.png "Leather wallet ad, quiet luxury, 30 seconds." --category "leather wallet" --model wallet.glb

:: Make a run's ad again from its inputs (after a failure, or with newer code)
.venv\Scripts\python -m pipeline.agents.producer --again runs\20261101-223512-ad-sable_wallet

:: The eight demo ads; the 30-product batch; numbers from the run logs
.venv\Scripts\python scripts\demo_ads.py
.venv\Scripts\python scripts\batch_ads.py
.venv\Scripts\python scripts\evaluate.py --since 20261101

:: Runs: list, show, replay; old runs' heavy files cleaned (a dry run unless --yes)
.venv\Scripts\python -m pipeline.runs
.venv\Scripts\python -m pipeline.cleanup --days 7
```

Other options: `--critic` adds the critic loop, `--director live` lets Spark drive the Studio command by command, and `--preview` stops at the storyboard.

## The critic (optional)

With `--critic`, every ad is judged and revised before its final render. The critic **measures first and judges second**:

- **Measured, exact.** The Studio renders each frame three ways: as is, without the product's shadow, and without the product. The difference gives the product's exact pixels. From them it measures how much of the frame the product fills and which edges cut it, outline lost in the background, blown highlights and crushed shadows, distance from the brand's colours, and titles over the product. At every cut it reads how far the camera turns and whether the lights change.
- **Judged, by vision.** Muse Spark Open sees each shot's frames with those numbers, the brief and the brand. It scores composition, lighting, product visibility, brand, continuity and titles from 0 to 10, against written anchors. A second pass judges the whole ad.
- **Bound by the measurements.** A major measured fault must appear in the critique, scored 6 or less, or the answer goes back to the model. A shot passes when every score is 7 or more, decided in code. Near the pass mark it is judged twice and the worse result kept.

Its fixes are storyboard edits (`shots[1].camera.fill 0.9 -> 0.65`), applied by the director through tools that check them against the schema. The loop revises up to 3 times and keeps its best round. In tests it took a broken ad from 1 of 5 shots passing to 5 of 5. Muse Spark Open agreed with itself on pass/fail 84% of the time, against 89% for Muse Spark, at the same speed, so the critic runs on the open-weights model.

## The Studio

`build\Release\Studio.exe` is the renderer the agents drive. It serves **JSON-RPC 2.0 over WebSocket** on `127.0.0.1:7468` (`--port N` for another), and writes the URL with a per-run token to `server.json` next to the exe. The method is the command and the params are its arguments:

```json
-> {"jsonrpc": "2.0", "id": 1, "method": "camera.move", "params": {"move": "orbit", "subject": "product",
    "start": 0, "duration": 4, "azimuth": -40, "to_azimuth": 40, "elevation": 8, "fill": 0.6}}
```

`commands.list` describes every command and its arguments. A failed command changes nothing and says which argument is wrong and what it accepts. Options: `--hidden` (no window; how the pipeline runs it), `--demo-scene`, `--width W --height H`, `--check out.png`, `--view NAME` (albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe, lights).

<details>
<summary>The Studio's commands</summary>

| Command | What it does |
|---|---|
| `studio.reset` | Empties the stage: every entity destroyed; the environment, render settings and active camera reset |
| `environment.get` / `environment.set` | HDRI, image-based lighting, exposure, bloom, tone mapping (`aces`, `agx`, `neutral`), SSAO |
| `render.get` / `render.set` | Antialiasing, shadows, background colour |
| `camera.get` / `camera.set` | Creates or moves a camera and makes it the one the frame is seen through |
| `product.create` | A product spun from a profile: a template (`perfume`, `bottle`, `jar`, `can`, `dropper`) or your own parts, with colours and a label image wrapped round one part. A part can be glass (transmission, index of refraction, thickness, the colour of what it holds), clear-coated, or have its own specular |
| `backdrop.create` | A cyclorama or a round pedestal, optionally covered with a texture |
| `lighting.preset` | A lighting setup around a subject: `three_point`, `rim_dark`, `high_key`, `top_soft`, `split`, `neon_dual`, `overhead_soft`, `edge_rim`; `glow` adds a pool of light behind it |
| `camera.move` | A shot's camera move around a subject: `static`, `orbit`, `dolly`, `crane`, `truck`, `reveal`, `zoom`, or `path` through up to 8 waypoints on a curve that never overshoots. `fill` is the subject's share of the frame's height, so a jar and a bottle frame alike. `aperture` sets a shallow focus that keeps the subject sharp. Moves placed end to end are cuts |
| `timeline.set_track` / `add_key` / `remove_track` / `clear` / `get` | Keyframes any number, vector or colour field of any component, with easing (linear, in, out, in_out, step, cubic bezier) |
| `timeline.seek` / `play` / `pause` | The scene at a time; real-time playback in the window |
| `text.create` / `set` / `remove` / `get` / `measure` | Titles drawn over every frame: five open-licensed fonts, size as a share of the frame's height, anchor, colour, letter spacing; opacity, offset, scale and tracking can be animated |
| `shot.preview` | Renders the frames at given times as PNGs |
| `shot.render` | Renders a time range straight into an `.mp4` (through ffmpeg) or as PNG frames; `shutter` spreads each frame's samples over the shutter's time for motion blur |
| `shot.bounds` | Where an entity is in the frame at a time: its box, centre, share of the frame, and which edges cut it |

Plus the engine's own commands: `entity.create`, `component.set`, `scene.save`, `history.undo`, and more.

Frames render offscreen at any size, each from scratch at its time, so a frame looks the same alone or in a sequence. On an Intel Iris Xe a 1080p frame with motion blur takes about 0.5 s. A render blocks the Studio, so clients should turn off WebSocket ping timeouts.

</details>

## Repository layout

```
Studio/main.c               the Studio program
Engine/                     the Studio library (C): commands, timeline, camera moves, paths and framing,
                            lighting presets, products and backdrops (glTF), labels, titles (SDF fonts),
                            offscreen shot rendering with motion blur; tests/
pipeline/
  meta/                     clients for Muse Spark, SAM 3.1, Muse Image, Muse Voice and Baseten: caching,
                            retries, outage waits, cost tracking
  catalog/                  3D models (Sketchfab, Objaverse, Poly Haven), set surfaces and HDRIs, props
  agents/analyst/           the brand analyst: segmentation, palette, materials, traced shape, label and print
  agents/scout.py           finding the 3D model (and refusing branded ones)
  agents/stager.py          standing it the way the product stands
  agents/colourist.py       repainting it in the photo's colours
  agents/director/          the director: shot grammar, style library, rules, drafts, revisions, live mode
  agents/critic/            the critic: measurements, cuts, shot and whole-ad judgment, the loop
  agents/brief.py           the spoken brief
  agents/producer.py        the whole chain: photo + brief → ad
  studio/                   the Studio client; storyboard → commands; models, recolouring, reframing, rendering
  encode/                   the final cut, the end card, the music
  schemas/                  pydantic models: BrandProfile, Storyboard, Critique (JSON schemas in json/)
  runs.py, cleanup.py       run folders: log, outputs, replay; cleaning old ones
app/                        the web app: FastAPI backend, one HTML page
scripts/                    the demo ads, the 30-product batch, the evaluation, test photos, font kerning,
                            the API key setup
start.bat                   one-click setup and launch
tests/                      the pipeline's regression tests
Assets/                     fonts (OFL), HDRIs (CC0), shaders, test product photos
Deps/                       the engine (PBR_Engine) as headers and prebuilt libraries
docs/                       the architecture, the roadmap, two overview PDFs
```

**Tests:**
- `.venv\Scripts\python -m unittest discover -s tests -t .` runs the pipeline's 53 tests, with no GPU or network.
- `ctest --test-dir build -C Release` runs the Studio's timeline and text layout tests.
- `pipeline/meta/smoke/run_all.py` makes one test call to each model.

**More documentation:**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): each agent, the Studio and the rules in detail.
- [docs/ROADMAP.md](docs/ROADMAP.md): the plan, phase by phase, with what was done and what's left.
- [docs/Project_Overview.pdf](docs/Project_Overview.pdf) and [docs/Studio_Architecture.pdf](docs/Studio_Architecture.pdf): overviews of the project and the Studio.

## Built during the hackathon

The rendering engine (`PBR_Engine`, [AI-Powered-PBR-Renderer](https://github.com/Mar-Dev-One/AI-Powered-PBR-Renderer)) **existed before the hackathon** and is used here as a prebuilt library (`Deps/`). Its PBR shading, image-based lighting, shadows, bloom, TAA, SSAO, scene and command system all predate the event. During the hackathon, four rendering features were added to it on its `features/glass-and-focus` branch: glass (transmission, index of refraction, thickness, absorption), depth of field, clear coat and specular.

**Everything in this repository was written during the hackathon**, from 2026-10-27:

- **`Engine/`:** the Studio library: commands, the timeline and its tests, camera moves, paths and framing, lighting presets, procedural products and backdrops, labels, titles with SDF fonts and kerning, offscreen rendering to PNG and video, motion blur.
- **`Studio/main.c`:** the Studio program.
- **`pipeline/`:** every agent, the Meta model clients, the catalogues, the schemas, run folders, the final cut and its music.
- **`app/`:** the web app.
- **`scripts/`, `tests/` and `Assets/photos`:** the scripts, the tests and the test product photos (generated with Muse Image).

## Credits and licences

- **3D models:** downloaded per ad from Sketchfab, Objaverse and Poly Haven. Only CC0 and CC-BY models are used. Each CC-BY model's credit is saved with the run (`model_credit.json`) and shown in the app.
- **Sets and props:** surfaces, HDRIs and prop models from [Poly Haven](https://polyhaven.com), CC0.
- **Fonts:** Playfair Display, Montserrat, Oswald and Great Vibes, under the SIL Open Font License 1.1 (licences in `Assets/fonts`).
- **Music:** synthesized note by note by `pipeline/encode/music.py`: original, with nothing to license. A track placed at `Assets/music/<mood>.mp3` is used instead.
- **Brands:** every brand in the photos, ads and examples is fictional. Catalogue models showing a real brand are refused.
