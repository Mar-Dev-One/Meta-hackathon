# Roadmap

**The project:** a multi-agent pipeline that turns a product (a few photos) and a short brief
("luxury perfume ad, dark and moody, 15 seconds") into a finished 3D marketing video, rendered by
an agent-controllable PBR engine and checked frame by frame by a critic agent.

**The event:** Meta Global AI Developer Hackathon. Building runs **Tue Oct 27 to Wed Nov 4, 9:00 PM ET**.
Nov 3 is the last day for help with technical problems. Plan to be feature-complete on **Mon Nov 2**,
polished on **Tue Nov 3**, and to spend **Wed Nov 4** on the video and the submission only.

_Written 2026-10-27. Updated 2026-11-02: phases 1-7, 10 and 11 done; a 30-ad batch reviewed frame
by frame and its flaws fixed in [Phase 12](#phase-12-the-30-ad-batch-and-its-fixes-nov-1-2); the
README and [ARCHITECTURE.md](ARCHITECTURE.md) rewritten. What's left: the rest of Phase 12, then
phases 8-9._

---

## Contents

0. [Ground rules: what is new, what isn't](#0-ground-rules-what-is-new-what-isnt)
1. [Architecture](#1-architecture)
2. [Schedule at a glance](#2-schedule-at-a-glance)
3. [Phase 0: Setup and admin (Oct 27)](#phase-0-setup-and-admin-oct-27)
4. [Phase 1: The studio renderer (Oct 27-29)](#phase-1-the-studio-renderer-oct-27-29)
5. [Phase 2: Pipeline foundation (Oct 30)](#phase-2-pipeline-foundation-oct-30)
6. [Phase 3: Brand analyst (Oct 30-31)](#phase-3-brand-analyst-oct-30-31)
7. [Phase 4: Director (Oct 31 - Nov 1)](#phase-4-director-oct-31---nov-1)
8. [Phase 5: Asset generation (Nov 1)](#phase-5-asset-generation-nov-1)
9. [Phase 6: Critic loop (Nov 2)](#phase-6-critic-loop-nov-2)
10. [Phase 7: Final cut and the app (Nov 2-3)](#phase-7-final-cut-and-the-app-nov-2-3)
11. [Phase 8: Three ads, evaluation, freeze (Nov 3)](#phase-8-three-ads-evaluation-freeze-nov-3)
12. [Phase 9: Demo video and submission (Nov 4)](#phase-9-demo-video-and-submission-nov-4)
14. [Phase 10: Built beyond the plan (Oct 29-31)](#phase-10-built-beyond-the-plan-oct-29-31)
15. [Phase 11: Enhancements (Oct 31 - Nov 2)](#phase-11-enhancements-oct-31---nov-2)
16. [Phase 12: The 30-ad batch and its fixes (Nov 1-2)](#phase-12-the-30-ad-batch-and-its-fixes-nov-1-2)
17. [Phase 13: The voice-over and the 50-ad batch (Nov 2-3)](#phase-13-the-voice-over-and-the-50-ad-batch-nov-2-3)
18. [Risks and fallbacks](#risks-and-fallbacks)
19. [Cut list if behind](#cut-list-if-behind)
20. [After the hackathon: the engine's module system](#after-the-hackathon-the-engines-module-system)

---

## 0. Ground rules: what is new, what isn't

The rules say the demo must show only what was built during the event, and judges must be able to
tell new work from old, or the project is disqualified.

- **The engine predates the hackathon.** `AI-Powered-PBR-Renderer` has commits from 2026-07-21.
  It is used here as a **prebuilt dependency** (`Deps/`) and is **not modified during the event**.
- **This repository is the hackathon work.** First commit 2026-10-27 11:15. Everything new goes here:
  `Engine/` (the studio: timeline, text, products, shot rendering), `Studio/` (the renderer app),
  `pipeline/` (the agents) and `app/` (the UI).
- **Don't reuse the engine's removed `pbr_agent` code** from its git history. The agents are written new.
- **Ask in #questions** whether a solo participant may use their own pre-existing engine as a
  dependency with all new work in a separate repo. Keep the answer (a screenshot) in `docs/`.
- **Both repos public.** Judges can't review a `.lib`; make `AI-Powered-PBR-Renderer` public too.
- **Rights to everything:** fictional brands (or products you own) in every demo ad, never a real
  logo; CC0 HDRIs (Poly Haven); OFL or Apache fonts; royalty-free music with a licence you keep in
  `docs/licenses/`.
- The README gets a **"Built during the hackathon"** section listing every folder and feature,
  and the demo video says it out loud.

---

## 1. Architecture

```
              brief (text or voice) + product photos
                               │
             ┌─────────────────▼─────────────────┐
             │ Producer (orchestrator, Python)   │  run folder: every input, output, frame, score
             └──┬──────────┬───────────┬─────────┘
                │          │           │
   ┌────────────▼──┐ ┌─────▼──────┐ ┌──▼─────────────┐
   │ Brand analyst │ │ Director   │ │ Critic         │
   │ SAM 3.1       │ │ Muse Spark │ │ Muse Spark     │
   │ Muse Spark    │ │ (tools)    │ │ vision, SAM 3.1│
   └──────┬────────┘ └─────┬──────┘ │ + geometry     │
          │ brand profile  │ tool    └──▲──────┬─────┘
          │                │ calls      │frames│ fixes
          │       ┌────────▼────────────┴──┐   │
          └──────►│ Studio renderer (C)    │◄──┘ (back to the Director)
     Muse Image ─►│ JSON-RPC over WebSocket│
     (textures)   │ timeline, text, shots  │
                  └──────────┬─────────────┘
                             │ PNG frames
                       ffmpeg → MP4 (+ music, end card)
```

### Repository layout (target)

```
Meta-hackathon/
  Engine/                     C, static library Meta_Engine (all new)
    src/Studio/               host commands for camera, environment, render settings, scene reset
    src/Timeline/             keyframe tracks over any reflected field, easing, camera moves
    src/Text/                 SDF fonts, layout, screen and world text
    src/Products/             lathe and box meshes from profiles, label mapping, backdrops
    src/Shot/                 deterministic offscreen rendering of frames
    shaders/                  text.vert/frag, ...
    deps/                     stb_truetype.h
  Studio/main.c               the renderer app ("Studio"): hidden or windowed, command server
  pipeline/                   Python 3.11+ package (all new)
    studio/                   JSON-RPC client, typed wrappers for every command
    meta/                     clients: Muse Spark, Muse Spark Open, Muse Image, SAM 3.1, Voice
    schemas/                  pydantic models: BrandProfile, Storyboard, ShotPlan, Critique
    agents/                   brand_analyst.py, director.py, critic.py, producer.py
    prompts/                  one file per prompt, versioned
    encode/                   ffmpeg wrapper
    eval/                     test briefs, scoring runs
  app/                        local web UI (FastAPI + one HTML page)
  Assets/                     fonts/, hdri/ (studio HDRIs), music/, products/ (sample photos)
  docs/                       ROADMAP.md, ARCHITECTURE.md, licenses/
```

### Principles

- **The renderer is deterministic.** A frame is a function of (scene, timeline, time t, settings).
  The same shot re-rendered gives the same pixels, so the critic's fixes are measurable.
- **Agents never compute camera maths.** They pick from a shot grammar (orbit, dolly, crane, ...)
  and fill parameters; the renderer turns those into keys.
- **Everything the agents do is validated.** Tool arguments are checked by the server (it already
  rejects bad arguments with error codes); errors go back to the model to correct.
- **Every run is a folder** (`runs/<timestamp>/`): brief, brand profile, storyboard, every tool call,
  every preview frame, every critique, the final MP4. The UI and the demo replay from it.
- **Meta API calls are cached on disk** by a hash of the request, so reruns cost nothing and the
  demo can't fail on a network hiccup.

---

## 2. Schedule at a glance

_Updated 2026-10-31._ Phases 1-7 are done, days ahead of plan, and a lot was added that the plan
didn't have (Phase 10): products of any shape from a photo alone, a live director, real sets and
painted backgrounds, product motion, cuts on the beat, transitions, end cards. Every remaining
piece is split into steps of about 1-2 hours; each ends with something that can be checked, and
work stops for a report after each one.

| Date | Steps | Checkpoint |
|---|---|---|
| ~~Tue Oct 27~~ | ~~0, 1.1-1.5~~ done | ~~First MP4, written by hand~~ |
| ~~Wed Oct 28~~ | ~~1.6, 1.7a-1.7d, 2a-2c, 3a-3e, 4a-4e~~ done | ~~**First fully agent-made video**~~ |
| ~~Thu Oct 29~~ | ~~6a-6e, 7a-7d, 10.1~~ done | ~~**Critic fixes a broken shot on its own**; the app; any-shape products~~ |
| ~~Fri Oct 30~~ | ~~10.2-10.11~~ done | ~~Photo-only models; live director; sets, motion, painted backgrounds, beat cuts, end cards~~ |
| ~~Sat Oct 31~~ | ~~10.12-10.13, 11.1~~ done | ~~Positioning of any-shape models; textured models~~ |
| ~~Sun Nov 1~~ | ~~11.2, 11.3, 11.4; 8a demo ads; the 30-ad batch~~ done | ~~Models in the product's colours; resumable runs; 30 ads overnight~~ |
| ~~Mon Nov 2~~ | ~~Phase 12 fixes from the batch; 8b evaluation; README and ARCHITECTURE.md; the voice-over; the 50-ad batch~~ done | ~~**Feature freeze at night**~~ |
| ~~Tue Nov 3~~ | ~~Phase 13 fixes from the 50-ad batch; start.bat sets up everything~~ done | ~~Fixes made and remade~~ |
| Wed Nov 4 | 8c release zip, clean clone; 9a video; 9b | Submitted by 6 PM ET (deadline 9 PM ET) |

### Step plan

Each step: what it delivers, and how it's checked. The phase sections below hold the details.

**Phase 1.7: Text in the Studio** (so the critic sees titles in the frames)

| Step | Delivers | Checked by |
|---|---|---|
| ~~1.7a~~ done | `stb_truetype` vendored; 3-4 OFL fonts in `Assets/fonts` (serif, geometric sans, condensed, script) with licences; SDF glyph atlas | The atlas dumped to a PNG looks right |
| ~~1.7a+~~ done | Kerning: these fonts keep it in GPOS lookups `stb_truetype` misses (Playfair AV -5% em). A fontTools script writes each font's pairs to `<font>.kern.json`; `font_kerning()` reads it | "AV", "To", "Wa" drawn closer in the sample renders |
| ~~1.7b~~ done | Text drawn into shot frames after the scene: anchor, size as a share of frame height, colour, tracking; `text.create` / `text.set` / `text.remove` | `shot.preview` shows a title, the same at 640 and 1920 wide |
| ~~1.7c~~ done | Text fields on the timeline (opacity, offset, scale, tracking): fades and reveals as keys | A title fading and rising in a rendered video |
| ~~1.7d~~ done | `text.measure`; `ads.py` titles moved from ffmpeg to the Studio; ffmpeg keeps only the fades | The five ads re-rendered with Studio titles |

**Phase 2: Pipeline foundation**

| Step | Delivers | Checked by |
|---|---|---|
| ~~2a~~ done | `pipeline/meta`: Muse Spark (text, vision, JSON, tools), SAM 3.1, Muse Image clients; disk cache; retries; token and cost tracking; Baseten switch | Smoke tests through the clients pass; a rerun is all cache hits; a bad model name gives a clear error |
| ~~2b~~ done | `pipeline/schemas`: pydantic BrandProfile, Storyboard, Shot, Critique, exported as JSON Schema | One `ads.py` ad expressed as a Storyboard validates and renders |
| ~~2c~~ done | Run folders (`runs/<time>-<slug>/`): inputs, outputs, frames, `log.jsonl` events; a reader for replay | A run of an `ads.py` ad leaves a complete, replayable folder |

**Phase 3: Brand analyst** (photo in, brand profile and 3D product out)

| Step | Delivers | Checked by |
|---|---|---|
| ~~3a~~ done | Segmentation: full-size masks and boxes for product, cap, label from SAM 3.1 | Overlays on 3 photos (Muse Image products, fictional brands) |
| ~~3b~~ done | Outline → profile: half-width per row, smoothed, scaled to a real height; the cap mask splits body and cap; → `product.create` | The 3D product rendered next to its photo, same angle |
| ~~3c~~ done | Label cut from the photo and unrolled from the curve; palette from the product's pixels | The label on the 3D bottle reads like the photo |
| ~~3d~~ done | Materials and mood from Muse Spark vision: per-part finish, typography, mood, "do not" rules | Valid JSON for the 3 photos |
| ~~3e~~ done | `BrandProfile` file and `analyse(photo)`; a contact sheet (photo, masks, curve, render) | 3 photos in, 3 products out that clearly match |

**Phase 4: Director** (brief and brand profile in, video out)

| Step | Delivers | Checked by |
|---|---|---|
| ~~4a~~ done | The shot grammar for prompts, generated from `commands.list` and the moves, presets and templates; a style library (6-8 looks with defaults) | A prompt-ready grammar file, small and complete |
| ~~4b~~ done | Brief → Storyboard with Muse Spark (JSON, validated, errors back to the model, 3 tries) | Storyboards for 3 different briefs that validate |
| ~~4c~~ done | Storyboard → Studio calls, in code (the `ads.py` runner generalized): no LLM needed to build a shot | The 3 storyboards render |
| ~~4d~~ done | Muse Spark tool calling for what the grammar doesn't cover (set dressing, light tweaks); revision mode: a shot edited from a critique | A shot changed by a written fix |
| ~~4e~~ done | `make_ad(brief, photo)`: analyst → director → render → finish | **First fully agent-made video** |
| 4f | Voice brief: Muse Voice Transcribe, then a Muse Spark clean-up pass | Done Nov 1: "Speak it" in the app |

**Phase 5: Assets** (done differently, see Phase 10)

| Step | Delivers | Checked by |
|---|---|---|
| ~~5a~~ replaced | ~~Muse Image backdrop textures~~ → a CC0 set library (surfaces, light environments) and **Muse Image painted backgrounds** made 360° light environments (10.7, 10.8) | ~~A cyclorama in generated marble, linen, velvet~~ |
| ~~5b~~ replaced | ~~Label art; end-card backgrounds~~ → the end card uses the product cut from the photo (10.11) | |
| 5c | Quality gate: Muse Spark vision checks an image fits the request and palette; one retry | _Not done; low priority_ |

**Phase 6: Critic** (done Oct 29)

| Step | Delivers | Checked by |
|---|---|---|
| ~~6a~~ done | Measured checks from an exact product mask: fill, cut edges, separation, clipping, palette distance, title overlap | ~~The known weak spots show up~~ |
| ~~6b~~ done | Vision scoring on the rubric, bound by the measurements; fixes as storyboard edits | ~~Scores and fixes for the five ads~~ |
| ~~6c~~ done | The loop: judge, revise, rebuild, up to 3 rounds, best kept; resumes after an outage | ~~A deliberately broken shot gets fixed (1 → 5 of 5 shots)~~ |
| ~~6d~~ done | Checks across cuts; a whole-ad pass every round | ~~A mismatched cut is flagged and fixed~~ |
| ~~6e~~ done | The critic on Muse Spark Open (default), compared with Muse Spark: 74% agreement, self-agreement 89% / 84% | ~~Documented~~ |

**Phase 7: Final cut and app** (done Oct 29-30)

| Step | Delivers | Checked by |
|---|---|---|
| ~~7a~~ done | Music synthesized per mood (or `Assets/music/<mood>`), 9:16 from the same storyboard; end card later (10.11) | ~~Both versions of one ad~~ |
| ~~7b~~ done | FastAPI backend: start a run, stream its events (SSE), serve its files | ~~A run started from `curl` streams~~ |
| ~~7c~~ done | The page: photo and brief in, format, director, 3D model; profile, storyboard, critic rounds, videos, log; progress bar | ~~A run from the browser~~ |
| ~~7d~~ done | Replay: any run's events at 1×, 2× or 4× | ~~A recorded run replays~~ |

**Phase 8: Freeze** -- ~~8a the demo ads end to end~~ done Nov 1 (`scripts/demo_ads.py`, and 30
more in the batch); ~~8b evaluation~~ done Nov 2 (`scripts/evaluate.py`: 72 runs, in the README);
8c ~~README and the architecture doc~~ done Nov 2 (`docs/ARCHITECTURE.md` replaces
`Studio_Architecture.pdf`), release zip, clean-clone test.

**Phase 9: Submission** -- 9a the 3-minute demo video from replayed runs; 9b submission by
6 PM ET, X post, gallery.

Sessions to attend: **Wed Oct 28, 12 PM ET: Agents 102: Best Practices for Verifiable Agents**
(the critic loop); **Fri Oct 30, 12 PM ET: Muse Open Models on Fireworks** (open-weight prize).
Office hours in Discord every weekday 10-11 AM ET: bring API questions there.

---

## Phase 0: Setup and admin (Oct 27)

### Admin
- [ ] Claim the **$150 Meta Model API credits** (form, then a card on the Billing page, then a spend limit).
- [ ] Request **Baseten** ($100, up to 2,000 people) and **Modal** ($100, first 1,000) credits now.
      On Baseten use `meta-models/muse-spark-open-1026`, not the name in their docs.
- [ ] Request **Fireworks** credits ($25, shortlisted teams).
- [ ] Post in #intros; ask the pre-existing-engine question in #questions.
- [ ] Make both repos public (or schedule it before submission, with a reminder).
- [x] Read the Meta API docs: model list, Quickstart, cookbook. Note for each model: input and
      output formats, limits, price. Check whether **Muse Wonder** does something useful here
      (video, 3D or world generation) and write the finding in `docs/ARCHITECTURE.md`.
- [x] One test call each to Muse Spark (text, vision, tool calling), Muse Image, SAM 3.1,
      Muse Voice Transcribe and Muse Spark Open, saved as scripts in `pipeline/meta/smoke/`.

### Repo
- [ ] `docs/ARCHITECTURE.md`: the diagram above, the command list (Phase 1), the schemas (Phase 2).
- [ ] README: "Built during the hackathon" section (kept up to date every day).
- [ ] `.gitignore`: `runs/`, `cache/`, `build/`, `.venv/`, `.env`.
- [x] `.env.example` with the API key names; keys never committed.

**Done when:** every Meta model has answered one smoke-test call from this machine.

---

## Phase 1: The studio renderer (Oct 27-29)

All C work, in `Engine/` (library `Meta_Engine`) and `Studio/main.c`. No engine changes.

### 1.1 Library and app setup (Oct 27)
- [x] `Engine/CMakeLists.txt`: static library `Meta_Engine`, links `PBR_Engine`; `Testbed` links it.
- [ ] Post-build copy of `Engine/shaders` and `Assets/fonts` next to the exe.
- [x] Rename the program to **Studio** (`Studio/main.c`): an empty scene by default (the material grid
      moves behind `--demo-scene`); `--hidden` for running as the agents' renderer;
      `--width/--height` for the output resolution, independent of the window.
- [x] Register host commands through `command_context.host_commands`: one table per area
      (`studio_commands()`, `timeline_commands()`, `text_commands()`, `product_commands()`,
      `shot_commands()`), concatenated in `main.c`.

### 1.2 Studio commands (Oct 27)

| Command | Arguments | Notes |
|---|---|---|
| `studio.reset` | — | Clears the world, timeline, texts; default environment |
| `environment.set` | any `scene_environment` key | via `deserialize_environment()`; HDRI bake via `ibl_cache_sync()` |
| `environment.get` | — | `serialize_environment()` |
| `render.set` | `bloom`, `tonemap`, `ssao`, `antialiasing`, `exposure`, `clear_color` | stored in the app's `scene_render_settings` |
| `camera.set` | `entity` or `position`, `target`, `fov_degrees` | makes a Camera entity the active one |
| `camera.look_at` | `entity`, `target` (entity or point) | sets rotation from a direction |
| `lighting.preset` | `name`, `subject`, `intensity`, `color_temperature` | see 1.6 |
| `texture.load` | `path` | loads a PNG/JPG under assets/ into a texture pool; returns an id |

- [x] Active camera: the frame renders through a chosen Camera entity (`world_camera_view()`),
      not the orbit camera; the orbit camera stays for the windowed mode.
- [ ] Studio HDRIs in `Assets/hdri/`: 3-4 CC0 studio and soft-light HDRIs (Poly Haven), small (1-2K).

### 1.3 Timeline (Oct 27-28)

The core of all animation. Writes any field of any component through `Reflect.h`:
`reflect_component_by_name()` → `reflect_field()` → `reflect_component_data()` + `offset`.

- [x] Data:
  ```c
  typedef enum ease { EASE_LINEAR, EASE_IN, EASE_OUT, EASE_IN_OUT, EASE_BEZIER, EASE_STEP } ease;
  typedef struct timeline_key   { f32 time; f32 value[4]; ease ease; f32 bezier[4]; } timeline_key;
  typedef struct timeline_track {
      char entity[ENTITY_NAME_MAX]; char component[32]; char field[48];   // "Transform", "position"
      uint32 width;                                                      // 1, 3 or 4 floats
      timeline_key* keys; uint32 key_count;
  } timeline_track;
  typedef struct timeline { timeline_track* tracks; uint32 track_count; f32 duration; } timeline;
  ```
- [x] `timeline_evaluate(tl, w, t)`: for each track, find the two keys around `t`, ease, interpolate,
      write the field. Before the first key: the first value; after the last: the last value.
- [x] Rotation: Euler degrees interpolated per axis (what Transform stores); the camera uses
      look-at targets instead (1.4), which avoids gimbal problems where it matters.
- [x] Fields that aren't plain floats (bool, enum, string) are rejected with a clear error.
- [x] Targets by **entity name**, resolved each evaluation, so tracks survive save/load and undo.
- [x] Commands: `timeline.set_track` (replaces keys), `timeline.add_key`, `timeline.remove_track`,
      `timeline.clear`, `timeline.get`, `timeline.seek` (evaluate and show at t), `timeline.play`,
      `timeline.pause`. The duration is the last key's time; shots set their own range when rendered.
- [x] Saved with the scene: `scene.save` / `scene.load` write and read `scenes/<name>.timeline.json` (through
      the command layer's `on_scene_file`; no separate commands needed).
- [x] Unit test (a small C test executable): evaluation at keys, between keys, each ease, clamping.

### 1.4 Camera move grammar (Oct 28)

Generators that write camera tracks from a few parameters. The director only ever uses these.

| Move | Parameters | What it produces |
|---|---|---|
| `static` | position, target, fov | one key per field |
| `orbit` | subject, radius, height, start/end angle, ease | position keys on a circle (sampled every 0.25 s), target = subject |
| `dolly` | subject, start/end distance, direction, ease | position along a line to the subject |
| `crane` | subject, start/end height, distance, ease | vertical move, looking at the subject |
| `push_past` | subject, side, distance | lateral move close to the product |
| `reveal` | subject, from (above/side/behind), ease | starts off the product, ends framed |
| `macro` | subject, point on the product, distance, fov | close detail with a narrow fov |
| `zoom` | start/end fov | fov keys only |

- [x] Command `camera.move` with `{ "move": "orbit", "start": 0, "duration": 4, ... }`.
- [x] Framing helper: `frame_subject(subject, fill)` picks a distance so the product's bounds fill
      a fraction of the frame (`world_bounds()` + fov). Every move uses it when distance isn't given.
- [x] Target track: the camera looks at a point that can itself be keyed (rack between product and logo).

### 1.5 Shot rendering (Oct 28)

- [x] Offscreen target at the output resolution (1920x1080, 1080x1920 for vertical, or a preview
      size): an RGBA8 framebuffer, `scene_renderer_resize()` to match.
- [x] Per output frame at time `t = start + i / fps`:
  1. `timeline_evaluate(t)`, `world_update()`;
  2. render **N sub-frames at the same t** (default 8) so TAA converges, with `delta_time = -1`
     the first time (exposure jumps, no adaptation) and fixed exposure;
  3. `scene_renderer_draw_to(target)`, then text (1.7) into the same target;
  4. read back with `rhi_read_pixels()`, flip rows, write PNG (`image_encode_png()`).
- [x] **Motion blur (stretch):** done Nov 1: `shutter` on shot.render/preview, the samples spread over it in steps averaged (each a short TAA run), final renders at 180 degrees (a third slower). accumulate sub-frames spread over a shutter interval
      (t, t + 0.5/fps) in a float buffer: anti-aliasing and motion blur from the same samples.
- [x] Commands:
  - `shot.preview { times: [...], width, height }` → PNG paths: the critic's input, fast.
  - `shot.render { start, end, fps, width, height, out_dir, samples }` → frame folder; progress
    events through the server's change notifications.
  - `shot.bounds { entity, time }` → the entity's screen-space box at t (0..1), and whether it's
    cut by the frame edge: the critic's geometric checks.
- [x] Determinism check: render the same frame twice, compare bytes (a test).
- [x] Found while building it: PNG compression costs ~0.6 s per 1080p frame, so `shot.render`
      also takes `video` (an .mp4) and pipes raw frames to ffmpeg: ~0.4 s per 1080p frame with
      16 samples on an Iris Xe. TAA restarts each frame, so frames are identical alone or in sequence.
- [ ] Progress events during `shot.render` (it blocks the Studio; clients turn off ping timeouts).

### 1.6 Products, backdrops and lighting (Oct 29)

Models built in code with `mesh_create()` and `material`s, registered with `assets_add_model()`.

- [x] **Lathe product:** a profile (list of (radius, height) points, bottom to top) revolved into a mesh
      with smooth normals and tangents; separate parts (body, shoulder, cap, label band) as submeshes
      with their own materials. Templates: `bottle`, `perfume`, `jar`, `can`, `tube`, `dropper`.
- [ ] **Box product:** rounded box with a texture per face (packaging, boxes, cartons).
- [x] **Label mapping:** a texture on a band of the body (cylindrical UVs between two heights, a
      wrap angle), from the brand profile's label image.
- [x] Glass: blended material (`MATERIAL_ALPHA_BLEND`), low roughness, tinted; the engine has no
      refraction, so choose demo products where that is acceptable (dark or frosted glass, opaque caps).
- [x] **Backdrops:** cyclorama (floor curving up into a wall), pedestal (cylinder, cube), plinth
      stairs, with optional textures from Muse Image.
- [ ] **Props:** builtin shapes plus a few CC0 glTF props (stones, leaves, silk) under `Assets/props/`.
- [x] Commands: `product.create { template, profile?, dimensions, parts: {body: {...}, cap: {...}},
      label?: { texture, from_height, to_height } }`, `backdrop.create`, `prop.create`,
      `material.set_texture { entity, slot, texture }`.
- [x] **Lighting presets** (`lighting.preset`), built from spot, point and directional lights placed
      relative to the subject's bounds: `three_point`, `rim_dark` (luxury), `high_key` (clean white),
      `top_soft`, `split`, `neon_dual` (two coloured rims). Colour temperature in Kelvin → RGB.
- [ ] Reflection probe around the set by default, so glossy products reflect the backdrop.

### 1.7 Text (Oct 29)

- [ ] `stb_truetype` SDF glyphs in an atlas (RGBA8 or a direct GL `R8` texture; no engine change).
- [ ] Layout: UTF-8, kerning, alignment, line breaks, wrapping, measurement.
- [ ] Screen-space text: anchor (9 positions) + offset, size as a fraction of frame height, so
      previews and the final render match.
- [ ] Style: colour, opacity, letter spacing, outline, soft shadow.
- [ ] World-space text (stretch): billboard or fixed, depth-tested.
- [ ] `Text` entries stored by entity name; their fields animatable by the timeline
      (`Text.opacity`, `Text.offset`, `Text.tracking`, `Text.scale`) so fades and reveals need no code.
- [ ] Fonts in `Assets/fonts/` (OFL): one serif (luxury), one geometric sans (tech), one condensed
      display face (bold/sport), one script. Licences in `docs/licenses/`.
- [ ] Commands: `text.create`, `text.set`, `text.remove`, `text.measure`.

**Phase 1 done when:** a Python script (no AI) builds a product on a cyclorama, applies `rim_dark`,
adds an orbit plus a macro shot and a fading title, renders 1080p frames and encodes an MP4 that
looks like an ad. **This video is the fallback demo from Oct 29 on.**

---

## Phase 2: Pipeline foundation (Oct 30)

Python 3.11+, `pipeline/` as an installable package (`pyproject.toml`), `uv` or `venv`.

- [ ] **Studio client** (`pipeline/studio/`): reads `server.json`, async WebSocket JSON-RPC,
      typed wrappers for every command, start/stop of `Studio.exe --hidden` as a subprocess.
- [ ] **Meta clients** (`pipeline/meta/`): one module per model; retries with backoff; a disk cache
      keyed by request hash; token and cost accounting per run; a switch between Muse Spark (API)
      and Muse Spark Open (Baseten) for any text or vision agent.
- [ ] **Schemas** (`pipeline/schemas/`, pydantic), also exported as JSON Schema for prompts:

```jsonc
// BrandProfile
{ "brand": "Noctis", "product_name": "Noir Absolu", "category": "perfume",
  "shape": { "template": "perfume", "profile": [[0.0,0.0],[0.031,0.0],[0.034,0.06],[0.012,0.08]], "height_m": 0.12 },
  "parts": { "body": { "base_color": "#1a1a22", "metallic": 0.0, "roughness": 0.05, "glass": true },
             "cap":  { "base_color": "#c9a45c", "metallic": 1.0, "roughness": 0.25 } },
  "palette": [ { "hex": "#0d0d12", "role": "background" }, { "hex": "#c9a45c", "role": "accent" } ],
  "logo": "runs/.../logo.png", "label": "runs/.../label.png",
  "typography": { "style": "serif", "case": "upper", "tracking": 0.2 },
  "mood": ["dark", "luxurious", "intimate"], "do_not": ["bright colours", "busy props"] }

// Storyboard
{ "title": "...", "duration_s": 15, "fps": 30, "aspect": "16:9", "style": "dark and moody",
  "music": "slow_piano", "shots": [
    { "id": "s1", "start": 0.0, "duration": 4.0, "intent": "reveal the silhouette from darkness",
      "camera": { "move": "reveal", "from": "above", "ease": "ease_in_out" },
      "lighting": { "preset": "rim_dark", "color_temperature": 3200, "intensity": 1.0 },
      "set": { "backdrop": "cyclorama", "texture": "black velvet", "props": [] },
      "text": [], "transition_out": "cut" } ] }

// Critique (one per shot per iteration)
{ "shot": "s1", "iteration": 2, "frames": ["t=0.5", "t=2.0", "t=3.5"],
  "scores": { "composition": 7, "lighting": 5, "product_visibility": 9, "brand": 8, "continuity": 8 },
  "pass": false,
  "issues": [ { "severity": "major", "category": "lighting", "frame": "t=2.0",
                "problem": "rim light too weak: the cap's edge merges with the background",
                "fix": "raise the rim light intensity by about 60% or warm it to 2800K" } ] }
```

- [ ] **Run folder** (`runs/<timestamp>-<slug>/`): `brief.json`, `brand_profile.json`,
      `storyboard.json`, `shots/<id>/iter_<n>/{tool_calls.json, frames/*.png, critique.json}`,
      `final/ad.mp4`, `log.jsonl` (every event with a timestamp, for the UI and replay).

---

## Phase 3: Brand analyst (Oct 30-31)

Input: 1-5 product photos, optional brand name and website text. Output: `BrandProfile`.

- [ ] **Segmentation with SAM 3.1:** prompt "product" (or the category) on each photo → product mask;
      then the parts: "cap", "label", "logo" → part masks.
- [ ] **Palette:** k-means in Lab space over the product mask pixels (and separately the label);
      roles (dominant, accent, text) assigned by area and contrast.
- [ ] **Silhouette to profile** (the creative trick): for upright, round products, take the product
      mask of the front photo, measure the half-width per row about the vertical axis, smooth it,
      scale to a real height (from the category's typical size or user input) → the lathe profile.
      SAM 3.1's mask literally becomes the 3D shape.
- [ ] **Label and logo:** crop the label mask from the photo, unwarp the cylinder curvature
      (inverse of the lathe mapping), clean edges → `label.png`; logo crop → `logo.png` (alpha from mask).
- [ ] **Materials and mood:** Muse Spark vision on the photo + masks: per part, metallic/roughness/
      glass guesses, the typography style, mood words, and "do not" rules. Constrained to the schema.
- [ ] **Template choice:** the category and silhouette decide lathe vs box (box for packaging).
- [ ] Debug output: a contact sheet (photo, masks, palette swatches, profile curve, the rendered
      3D product next to the photo) saved in the run folder. This makes a great demo moment.
- [ ] Fallbacks: no clean silhouette → template profile by category; no label → Muse Image label art
      from the palette and brand name.

**Done when:** 3 different product photos produce brand profiles and 3D products that look clearly
like the photos in a turntable render.

---

## Phase 4: Director (Oct 31 - Nov 1)

Two steps, so creative decisions and tool calls are separate and each can be checked.

### 4.1 Brief → storyboard (Oct 31)
- [ ] Prompt: the brief, the brand profile, the **shot grammar** (the moves, presets, backdrops,
      fonts, text styles the renderer offers), ad-craft rules (open strong, product visible within
      2 s, end on the product with the brand name, 3-6 shots for 15 s, cuts on motion).
- [ ] Output: `Storyboard` JSON, validated by pydantic; invalid → errors back to the model, up to 3 tries.
- [ ] Checks in code: shot durations sum to the ad's length, the last shot is the brand end card,
      every preset and move name exists, text fits on screen (`text.measure`).
- [ ] Style library: 6-8 styles with defaults (`luxury_dark`, `clean_minimal`, `bold_energetic`,
      `natural_organic`, `tech_sleek`, `playful_pop`) as starting points the director adapts.
- [x] **Voice brief:** Muse Voice Transcribe on a recorded brief → the same text input. Done Nov 1: "Speak it" in the app (`POST /transcribe`, `pipeline/agents/brief.py`); Muse Spark mends the mishearings ("and on the battle" → "end on the bottle"), the text lands in the brief to check.

### 4.2 Shot → tool calls (Nov 1)
- [ ] Muse Spark with **tool calling**: the tools are the studio commands (generated from
      `commands.list`, which already describes every argument). One shot at a time, given the shot,
      the brand profile and the previous shot's final state (for continuity).
- [ ] Execution: each tool call runs against the studio; errors (`invalid_args`, `not_found`, ...)
      go back to the model; the call log is saved.
- [ ] Shots are built on one shared set where possible (same backdrop and product), each shot
      owning its time range on the timeline; a shot that needs a different set uses `studio.reset`
      and its own scene file.
- [ ] After building: `shot.preview` of 3 frames (start, middle, end) for a quick self-check
      before the critic sees it.
- [ ] **Revision mode:** given a critique, the director edits the shot (changes keys, lights,
      text) instead of rebuilding it, using history transactions so a bad revision can be rolled back.

**Done when (Nov 1):** "luxury perfume ad, dark and moody, 15 seconds" + product photos → an MP4,
with no hand edits.

---

## Phase 5: Asset generation (Nov 1)

- [ ] **Muse Image** for: backdrop textures (velvet, marble, concrete, linen, gradient paper),
      tileable where possible; set dressing images (a blurred backplate behind the set);
      label art when the photo has none; end card backgrounds.
- [ ] Prompts built from the brand profile (palette hex values, mood) and the shot's intent.
- [ ] A tool `asset.generate { kind, description }` for the director, returning a texture path;
      results cached and reused across shots for consistency.
- [ ] Quality gate: Muse Spark vision checks a generated image matches the request and palette
      before it's used; one regeneration at most.
- [ ] **Muse Wonder:** if the Phase 0 check found it useful (e.g. image or world generation for
      backplates), use it here. That also qualifies for the Best Creative Build prize.

---

## Phase 6: Critic loop (Nov 2)

The critic is what makes the system trustworthy: it checks with measurements first and with
vision second, and every fix it asks for is verified on the next render.

### 6.1 Checks
| Category | Measured (exact) | Judged (Muse Spark vision) |
|---|---|---|
| Product visibility | `shot.bounds`: fraction of the frame the product fills, cut by an edge or not; SAM 3.1 mask of the rendered frame: visible fraction | Is the product the clear subject? |
| Composition | product centre vs rule-of-thirds lines; headroom; text box overlap with the product box | Balance, negative space, leading lines |
| Lighting | luminance histogram of the product mask vs the background (separation); clipped highlights | Rim present, shape readable, mood matches the brief |
| Brand consistency | Lab distance between rendered product colours and the profile palette; logo visible in the end card (SAM 3.1 "logo") | Fonts and colours match the brand |
| Continuity | lighting direction and colour temperature between the last frame of shot i and the first of shot i+1; screen direction of motion | Does the cut feel like the same ad? |

- [ ] Rubric: each category 0-10 with written anchors (what a 3, 6, 9 look like); a shot passes
      when every category is ≥ 7 and no major issue remains.
- [ ] Muse Spark vision gets: the frames (3 per shot at preview resolution), the brief, the brand
      profile, the shot's intent, **and the measured numbers**, so its judgment is grounded.
- [ ] Output: `Critique` JSON with specific, actionable fixes in renderer terms ("raise the rim light
      by 60%", "move the camera 20% further", "move the title to the top third").

### 6.2 Loop
- [ ] Producer: build shot → preview → critique → (pass) next shot, (fail) director revision → ...
- [ ] At most 3 revisions per shot; keep the best-scoring iteration if none passes.
- [ ] Oscillation guard: the director sees all previous critiques of the shot, so it doesn't undo a fix.
- [ ] A final whole-ad critique after all shots pass: pacing and continuity across cuts.
- [ ] **Open-weight variant:** the critic runs on **Muse Spark Open** (Baseten or Modal) with a flag;
      document which agent runs where, for the Best Open Weight Models prize.
- [ ] Logged: score per category per iteration → the UI shows scores rising.

**Done when:** a deliberately broken shot (product cut off, rim light off) is fixed by the loop
with no human input, and the before/after frames are in the run folder.

---

## Phase 7: Final cut and the app (Nov 2-3)

### 7.1 Final cut
- [ ] Final render of every passing shot at 1080p (or 1080x1920 for vertical social cuts),
      8+ samples per frame, motion blur on if done.
- [ ] ffmpeg: H.264, `yuv420p`, CRF 16-18, `+faststart`; transitions (`xfade` dissolves where the
      storyboard asks); music from `Assets/music/` chosen by style, faded in and out, cut to length.
- [ ] End card: logo + product name + tagline in the brand's font, rendered by the studio (not ffmpeg).
- [ ] Exports: 16:9 and 9:16 from the same storyboard (re-framing with the framing helper).

### 7.2 The app (`app/`)
- [ ] FastAPI backend that starts the studio and runs the producer; one HTML page (no build step).
- [ ] Screens: upload photos + brief (text or voice) → brand profile card (masks, palette, 3D product)
      → storyboard as a strip of shot cards → live log of agents (director tool calls, critic scores
      per iteration with the frames) → final video with download.
- [ ] Replay mode: open any run folder and play it back with its timing (for the demo video).

---

## Phase 8: Three ads, evaluation, freeze (Nov 3)

### 8.1 The demo ads (fictional brands, Muse Image product photos in `Assets/photos/`)
| Ad | Product | Brief | Shows off | Status |
|---|---|---|---|---|
| 1 | Perfume "Aurelle" | timeless, warm and intimate, 15 s | traced glass and label, fireplace set, drop and turn, dip, end card | good (Oct 30) |
| 2 | Face cream "Mira" | a calm spa morning, 12 s | **painted background**, float, both formats | good (Oct 30) |
| 3 | Olive oil "Solana" | a Mediterranean family kitchen, 12 s | painted place, warm light | plan good; render it |
| 4 | Coffee mug "BREW" | a cosy sunlit kitchen morning, 12 s | non-round model found online, painted kitchen | good (Oct 31) |
| 5 | Running shoe "STRIDE" | energetic, fast, 12 s | non-round model stood from the photo, bold set, fast cuts | good (Oct 31); truck slide to fix |
| 6 | Game controller "VOLT" | bold, neon, 12 s | a flat product filmed from above | needs 11.2 colours (model is orange) |
| 7 | Headphones "NOVA" | sleek, premium, minimal, 15 s | thin product, three-quarter staging | re-brief for a dark studio |

Nothing here needs rights we don't have: every brand is fictional, every photo made by Muse Image,
every set CC0, every model CC0 or CC-BY with its credit kept in the run (`model_credit.json`).
The iPhone tests (real brand) stay out of the demo.

Nov 1-2: `scripts/demo_ads.py` made the eight ads above, and `scripts/batch_ads.py` 30 more for 30
new fictional products (Phase 12). The strongest for the demo: GROVE, BOLT, FROST, COVE, KOVA,
RIPPLE, LUMEN. Kept out: ads whose catalogue model showed a real brand (PURA, RALLY, SNAPPA) or
the wrong shape (AERO, DRIFT, HALO, QUILL, NOIR).

### 8.2 Evaluation (numbers for the demo and README)
- [x] Done Nov 2: `scripts/evaluate.py` reads every run's log: ads made, time and cost per ad, the
      director's drafts and the problems the next draft fixed, where the time goes, how the 3D
      model was found (72 runs since Nov 1: in the README).
- [ ] A small blind comparison: one-shot director vs director + critic, frames side by side.

### 8.3 Freeze
- [x] Done Nov 2: README (what it does, how to run, how it works, results and limits, Meta models,
      **built during the hackathon vs before**, licences) and `docs/ARCHITECTURE.md`. Left: a GIF.
- [ ] Prebuilt Windows release (zip with `Studio.exe`, assets, Python app instructions).
- [ ] Clean clone + build + run on a second machine or a fresh folder.
- [ ] Tag `submission`.

---

## Phase 9: Demo video and submission (Nov 4)

### 9.1 Three-minute video (Demo is 25% of the score)
| Time | Content |
|---|---|
| 0:00-0:15 | A finished ad plays full screen. "A studio shoot costs thousands. This cost a brief and a photo." |
| 0:15-0:45 | Upload a photo, speak the brief: SAM 3.1 masks, palette, the silhouette turning into the 3D product |
| 0:45-1:30 | Director writes the storyboard; shots built live; the critic flags "product cut off", the fix lands, scores rise |
| 1:30-2:15 | The three ads, back to back (the payoff) |
| 2:15-2:45 | Architecture in one slide: which Meta model does what; what was built this week vs the existing engine |
| 2:45-3:00 | Impact: small brands and makers; call to action, repo link |

- [ ] Record from replayed runs (no live API risk); voice-over recorded separately.
- [ ] Upload (YouTube unlisted or similar), check the link while logged out.

### 9.2 Submission
- [ ] Submit on the CV platform **by 6 PM ET** (the deadline is 9 PM ET): repo link, video link,
      every team member listed, the track (Indie Developer), the problem statement (Build for Your World).
- [ ] Flag for: Best Agentic Use-Case, Best Creative Build (Muse Image), Best Build on Meta Open
      Weight Models (if the critic runs on Muse Spark Open).
- [ ] Post the demo on X (Most Viral, counted until Nov 8), link the post in the submission.
- [ ] Gallery page for the community vote; share it after Nov 9.

---

## Phase 10: Built beyond the plan (Oct 29-31)

Not in the original plan; each was built, tested on real products and committed.

| # | What | Where |
|---|---|---|
| ~~10.1~~ | **Products of any shape:** a 3D model found online (Sketchfab, Objaverse, Poly Haven; CC0/CC-BY only, credits kept) or uploaded as a .glb, fitted to the product's real size | `pipeline/catalog/`, `pipeline/studio/models.py` |
| ~~10.2~~ | **From the photo alone:** Spark decides round (traced, keeps the label) or not; searches; picks the closest model from a sheet of thumbnails | `pipeline/agents/scout.py` |
| ~~10.3~~ | **Staging:** Spark stands the model as in the photo (six ways up, seen from front and side; eight angles round, for three-quarter photos) | `pipeline/agents/stager.py` |
| ~~10.4~~ | **Live director** (experimental): Spark builds the whole film with all 50 Studio commands as tools, previews and refines it; turn budget, fallback when out of turns | `pipeline/agents/director/live.py`, `pipeline/studio/tools.py` |
| ~~10.5~~ | **Product motion** per shot: turn, float, drop, tilt; known to the critic | `Shot.motion`, `build.py` |
| ~~10.6~~ | **Light that sells the material:** rules for glass, metal, separation from the set, dark products before bright backgrounds; title contrast **measured on the rendered frame**; the critic's measurements of the hero guide Spark while it plans | `write.py` (`light_problems`, `title_contrast_problems`, `hero_problems`) |
| ~~10.7~~ | **Real sets:** 11 CC0 surfaces and 8 light environments from Poly Haven; the environment as a blurred real background; 5 styles built on them | `pipeline/catalog/sets.py`, `styles.py` |
| ~~10.8~~ | **Painted backgrounds:** Spark describes a place, **Muse Image** paints it, made a 360° light environment behind and around the product | `pipeline/studio/painted.py` |
| ~~10.9~~ | **Titles where the set is empty**, never on the pedestal's face | `write.py` |
| ~~10.10~~ | **Cuts on the beat** (the hero on a bar line), within every shot's limits; **dip-to-black** transitions | `encode/music.py` (`cut_to_beat`), `encode/finish.py` |
| ~~10.11~~ | **End card:** the film dissolves into the real product cut from the photo, the brand's name and tagline, in every format | `encode/endcard.py`, analyst's `packshot.png` |
| ~~10.12~~ | **Positioning:** thin products never filmed edge-on, flat ones always from above (measured along the model's own axes) | `write.py` (`edge_on`, `lies_flat`), `models.footprint` |
| ~~10.13~~ | **Textured models:** downloaded models keep their own textures (only glass is dressed), forced solid | `producer.with_model`, `models.opaque` |
| ~~10.14~~ | **Reliability:** hung renders time out and retry in a new Studio; taste rules warn instead of failing an ad; the director keeps its latest valid draft; logs written safely from several threads; the app's progress bar and periodic progress log | `client.py`, `render.py`, `runs.py`, `progress.py`, `app/` |

---

## Phase 11: Enhancements (Oct 31 - Nov 2)

Impact (how much better the ads or the submission get) and effort (S < 1 h, M a few hours,
L a day or more). Feature freeze **Mon Nov 2 at night**: after that, only fixes for the demo.

### 11.1 Quick wins (Oct 31)
| # | Improvement | Why | Impact | Effort |
|---|---|---|---|---|
| ~~11.1a~~ done | Truck slides keep the product in frame | long products slid half out (STRIDE); a slide is now capped to the room beside the product (`build.trucks_in_frame`) | High | S |
| ~~11.1b~~ done | A full run through the app | STRIDE, both formats, through `POST /runs`; every panel checked in a browser. Fixed: the run list failed on one broken old log (readers now skip a bad line); the progress estimate now counts each render's build, music and encoding | High | S |
| ~~11.1c~~ done | Bright environments tamed | the fireplace and city lights overwhelmed the product; now measured on the hero and brought down (exposure down, the product's light up by the same factor) before the titles are checked (`write.balance`) | Medium | S |
| ~~11.1d~~ done | Truer colours read from photos | a colour is its material's lit tone, without its shadows and highlights (`palette._lit`): lit materials 3-5 L* lighter and cleaner (Aurelle's amber, STRIDE's coral, ORBIT's strap); truly dark products (NOVA, VOLT, Solana) rightly unchanged | Medium | S |
| ~~11.1e~~ done | Shot variety check | 57 of 110 recent cuts were jump cuts (the same framing either side); a taste rule by the 30° rule (`write.jump_cuts`) and advice to vary framings: the next plan had none | Medium | S |

### 11.2 Quality (Nov 1)
| # | Improvement | Why | Impact | Effort |
|---|---|---|---|---|
| ~~11.2a~~ done | **Per-part colouring of models** | models wore their own colours (VOLT was orange, not black and lime); `studio/recolour.py` repaints a model in the photo's colours region by region (k-means in Lab over its surfaces, texture detail kept), paired by size and by lightness; the colourist (`agents/colourist.py`) shows Spark the photo, the model as made and each repainting, and keeps the closest, judging the main part first: VOLT, STRIDE, BREW repainted, ORBIT and NOVA kept as made | High | M |
| ~~11.2b~~ mostly done | Better music | mixed like a record (a stereo convolution reverb, clap and sidechain pump, a breath before the hero hit, soft saturation, every mood at -16 LUFS: they were -18.5 to -13.8), and Spark chooses each ad's mood, tempo and key (`storyboard.music`), which the synth and the beat snapping follow. Left, optional: real CC0 tracks in `Assets/music/` with beat detection (needs an ear) | High | S-M |
| ~~11.2c~~ done | Model choice by render | Spark ranks its top 3 thumbnails; the scout downloads them, renders each alike in the Studio (two side views, one from above; columns in an order of their own, so the first isn't a hint) and Spark picks by the renders (`scout.audition`), falling back to the thumbnail pick; ~30 s more. It caught headphones with bare discs for cups and a too-thick watch case | High | M |
| ~~11.2d~~ done | Props from the catalogue | 21 CC0 Poly Haven props at real size (`catalog/props.py`: stones, shell, succulent, fruit, croissant, vases, pots, wood); `look.props` places each by angle and gap, never overlapping the product, on the pedestal if it fits whole else on the floor clear of it (`build.prop_spots`); grammar section; rules: a prop with no floor to stand on (hard), props hiding >15% of the product in a shot (measured, `write.prop_problems`). Spark gave BREW a croissant behind it and ORBIT none. No fabric: none is CC0 | High | M-L |
| ~~11.2e~~ done | Model quality filter | finalists under 200 or over 1M faces left out before the render pick (`scout.FACES`); once stood up, what a model came standing on (a coaster, a stand, a ground plane: a thin slab at its bottom the rest stands on, as wide as half the product) is taken off (`models.strip_base`), its own flat bottom kept. Tested on every model used: only BREW's coaster went. See-through needs nothing: fit makes every non-glass model solid | Medium | S-M |
| ~~11.2f~~ done | Gentler 9:16 reframing | a wide product in 9:16 was held by the width: every shot the same, edge to edge (STRIDE ~0.84 of the width whatever its fill). `reframe.roomier` measures the product in each shot (shot.bounds) and scales all fills but close-ups by one factor until the widest spans 0.68 of the width, the shots keeping their differences (STRIDE now 0.46-0.62); 2-4 s per ad | Medium | S-M |
| ~~11.2g~~ done | Materials per part from the photo | since models keep their own materials (11.1), most carry their modeller's finish per part (ORBIT: steel, leather, glass); what was left: materials with none (glTF's default, metallic 1 roughness 1: dull grey metal) take the photo's finish (`models.finish_unset`), a modeller's kept | Medium | M |
| ~~11.2h~~ done | Lighting presets for dark and flat products | two Studio presets: `overhead_soft` (a big soft light from above, a front fill, a kicker: a flat product's top reads) and `edge_rim` (bright rims both sides and above behind: a dark product's outline reads on any set); taste rules point to them for a dark product under a preset that misses its outline and a flat one under side lights. Spark took edge_rim for ORBIT unprompted | Medium | M |

### 11.3 Reliability (Nov 1)
| # | Improvement | Why | Impact | Effort |
|---|---|---|---|---|
| ~~11.3a~~ done | Resume a run after a network outage | Meta calls wait out ~10 min of outage (was 2), downloads ~3 min (they had no retries; a cut-off download starts again); `producer --again RUN` and the app's "Make again" re-make a run from its inputs (`runs.inputs`; the brief event now logs critic, video, size; an uploaded .glb is kept), Spark's answers cached: a BREW re-make replayed all 12 calls at $0. The stall was the Studio (timeouts since 10.x) | High | M |
| ~~11.3b~~ done | Regression tests | `tests/` (stdlib unittest, `python -m unittest discover -s tests -t .`, ~5 s, no Studio, network or Spark): beat snapping over 400 random plans, every mood's loudness, tempo ranges, prop placement, the rules, base stripping, recolouring, 9:16 scaling, broken log lines; 25 tests. They found a real bug: snapping could stretch a shot past 5 s (a hero to 5.6 s): fixed, 0 broken in 3000 plans | High | M |
| ~~11.3c~~ done | Faster runs | measured first: checks took seconds, the render over half of every ad. 8 samples per frame instead of 16 (54-55 dB PSNR, indistinguishable, still and moving): renders 2x faster. And recolouring went from ~7 min to ~13 s for ORBIT: shared materials were repainted once per mesh (55 times, not 8), and the colour maths now runs per distinct colour. ORBIT: 847 s -> 430 s | Medium | M |
| ~~11.3d~~ done | Clean up leftover scenes, HDRIs and check renders | `python -m pipeline.cleanup` says what would go, `--yes` removes it (older than `--days`, default 1): the Studio's generated meshes, models copied in, painted backgrounds, check renders, runs' on-the-way model copies and raw videos; all made again when needed, every run still opens and can be made again. 888 MB found | Low | S |

### 11.4 Showcase (Nov 2)
| # | Improvement | Why | Impact | Effort |
|---|---|---|---|---|
| ~~11.4a~~ done | "How Spark decided" panel in the app | a card at the top of a run: one entry per decision, in order (reading the photo, shape, model search, model choice by render, stance, colours, each draft and the problems that sent it back, light balancing, the plan: set, light, props, music, shots, titles; music, result), each with Spark's reason and the sheets it chose from; built from the run's events in the page | High | M |
| ~~11.4b~~ done | Gallery of finished ads | "Gallery of finished ads" in the app (`GET /gallery`): every finished ad, end card as poster, brief, format, time, cost, a link to how it was made | Medium | S-M |
| ~~11.4c~~ done | Cancel and re-run in the app | Cancel (queued: never starts; running: stops at its next step, its Studio closed, status "cancelled") and Make again (the brief and format editable) on a run (`POST /runs/{id}/cancel`, `/again`) | Medium | S |
| ~~11.4d~~ done | Before/after of each fix in the app | each draft saved (`drafts/draft_N.json`) with its hero as measured; the panel shows each draft's problems, what Spark changed to fix the last one's, and its hero, one under the other | Medium | S |

### Later, or only if everything above is done
Frame by visible size (strapped watches end up tiny), contact shadows, reflective floors, sound
design, more transitions (match cuts, whip pans, light-flash cuts for energetic ads), a story-arc
check, animated titles, more environments and surfaces. Not this week: logo decals on 3D
models, voice-over: big and risky this late. Done Nov 1: free camera paths (`path`: 2-8 waypoints on a
monotone curve, no overshoot; offered in four styles: Spark opened AURELLE on one).

---

## Phase 12: The 30-ad batch and its fixes (Nov 1-2)

To see how the pipeline does on products it had never met, `scripts/batch_ads.py` made **30 ads
for 30 new fictional products** overnight, unattended: 15 seconds to 2 minutes, Muse Image photos
(`Assets/photos/batch/`). Ads up to 2 minutes came first: up to 30 shots, shots up to 8 s past 30 s,
minutes understood in briefs, long-form craft in the grammar. **23 of 30** were made in 4 h 44 min.
Every ad was then reviewed frame by frame (16-frame contact sheets), and its flaws fixed one by one,
each with a test, and the ads made again: **29 of 30** now.

### 12.1 Fixed (Nov 2)
| # | Flaw found | Fix | Where |
|---|---|---|---|
| ~~12.1a~~ | 7 ads failed with no reason kept | a failed run keeps its traceback (`traceback.txt`; where it broke in the event) | `runs.py` |
| ~~12.1b~~ | Shiny products crashed (MAREA, BOLT, SPARK) | highlight clusters compared by identity, not by value | `analyst/palette.py` |
| ~~12.1c~~ | A label past its part crashed (FROST into its lid; COVE called nearly all "cap") | the label goes on the part its band lies on most, kept to that part's side | `analyst/label.py` (`onto`) |
| ~~12.1d~~ | A stand in two pieces crashed (BREVA) | each mesh's base pieces taken off at once | `studio/models.py` (`strip_base`) |
| ~~12.1e~~ | **Real brands on catalogue models** (Colgate, Peugeot/Total, Polaroid) | the logo guard: Spark lists branded models (logo, lettering, title, a named real product) at the thumbnail pick and at the audition, and never uses one | `scout.py` |
| ~~12.1f~~ | A drone became a mushroom: no model fitted, so it was traced | a product that isn't round with no usable model stops (`NoModel`), asking for a .glb | `scout.py` |
| ~~12.1g~~ | An invented brand ("KEYCRAFT" for MONO) | the brand from the brief's capitals or the photo's file name; the directors told never to invent one | `producer.brand_hint`, `write.py`, `live.py` |
| ~~12.1h~~ | **Printed products came out blank** (BOLT's can, GROVE's tin, MAREA's engraving): SAM finds no paper "label" | print on the body found by colour (far from the body's, or from its neighbourhood's), wrapped as a see-through decal; no specks, seams or shading; cut to its full width | `analyst/label.py` (`printed`) |
| ~~12.1i~~ | **Colours washed out** (BOLT sky-pale, MAREA grey): `agx` was the default and Spark's choice in 27 of 47 storyboards | `aces` by default (measured closest to the photo on BOLT's hero); a taste rule against `agx` for a coloured product | `schemas/storyboard.py`, `write.py` |
| ~~12.1j~~ | **Liquids in glass went black** (RIPPLE's honey, VELVET, ZEST, LUMEN): clear glass only tinted the dark set behind | a coloured liquid shows its own colour (transmission at most 0.7): honey golden on any set | `schemas/brand.py` (`surface`) |
| ~~12.1k~~ | A model given with `--model` lost its CC BY credit | the `.credit.json` beside a catalogue model is used | `producer.py` |

### 12.2 Left (Nov 2, before the freeze)
| # | Flaw | Idea | Impact | Effort |
|---|---|---|---|---|
| ~~12.2a~~ done | Mid-ad dips to black look like glitches (6 ads) | dips of 0.4 s (were 0.7), only into the hero (`Storyboard.dips`); any other plays as a cut, so the jump-cut rule catches it | Medium | S |
| 12.2b | The audition rewards crude models (SABLE's flat card beat a detailed wallet) | tell it detail and craft beat small extras, which repainting covers | Medium | S |
| 12.2c | SCARLA (lipstick) never gets a valid hero in 3 tries | read its drafts; likely the hero rule against a thin product | Medium | S-M |
| 12.2d | Products stand as photographed, not as they'd rest (wallet, skateboard, knife, pen on end) | a resting-pose check: lie on the largest stable face unless the photo shows it standing | High | M-L |
| 12.2e | Long ads (1-2 min) vary little: the product small, few close-ups | measured variety rules past 30 s (share of close-ups, elevation spread) | Medium | M |
| 12.2f | Some recolourings miss (HAVEN tan, not olive) | look at the colourist's sheets for HAVEN | Low | S-M |
| ~~12.2g~~ done | The crossfade into the end card shows two titles at once | the film's titles fade out over 0.4 s, gone when the card dissolves in (`build.title_opacity`) | Low | S |

## Phase 13: The voice-over and the 50-ad batch (Nov 2-3)

The optional **voice-over** (`--voice`): Muse Spark writes timed lines, checked in code; Meta's MMS-TTS
speaks them locally; the music ducks under the voice. Then `scripts/voice_ads.py` made **50 ads with a
voice-over for 50 new products** overnight, unattended: a ring to a grand piano, glass, metal and rough
materials, 15 to 45 s. **41 of 50** were made (4 h 10 min, $12.60). Every ad was reviewed from its frames,
and four perfumes made by hand (AURUM, NOCTIS, SMERALDA, SOLARE) found more.

### 13.1 Fixed (Nov 3)
| # | Flaw found | Fix | Where |
|---|---|---|---|
| ~~13.1a~~ | A chandelier failed: a light key over the Studio's 1000 | light keys kept to the limit | `studio/build.py` |
| ~~13.1b~~ | A ring failed (2 cm, under the reader's 2 cm floor); every big product came out 0.6 m or less | the reader's heights as the profile allows, 0.005 to 5 m | `analyst/materials.py` |
| ~~13.1c~~ | A prop with nothing to stand on failed three drafts | taken out in code (`repair`) | `director/write.py` |
| ~~13.1d~~ | **Five products photographed head-on failed every draft** (motorbike, bicycle, scooter, boots, vacuum): the hero rule and the edge-on rule ruled out every angle | a three-quarter hero (30-60°) for a thin product end-on from the front; a hero turned too far brought within its limit in code; 340 read as 20 from the front | `director/write.py` (`hero_limit`, `repair`, `from_front`) |
| ~~13.1e~~ | Two Studios started at once raced on `server.json`, one timing out | each launch writes its own (`--server-json`) | `Studio/main.c`, `studio/client.py` |
| ~~13.1f~~ | NOCTIS's gold stopper came out smoked glass: its modeller made it part of the bottle's mesh | a mesh's connected pieces in the cap zone dressed as the cap (`split_caps`) | `studio/models.py` |
| ~~13.1g~~ | Black plinths glared white under rim lights, whatever their colour | a rough pedestal matte (`backdrop.create` takes `specular`) | `studio/build.py`, `Products.c` |
| ~~13.1h~~ | Lettering printed on glass was dropped (SMERALDA, SOLARE, NOCTIS) | looked for only in the logo SAM 3.1 finds, against the glass round it; kept only whole | `analyst/segment.py`, `analyst/label.py` |
| ~~13.1i~~ | A label on glass showed a refracted ghost under it | blended, drawn after the glass | `Products.c`, `Geometry.c` |
| ~~13.1j~~ | Engine changes didn't reach products built before (cached by request alone) | product files named with a format version | `Products.c` |
| ~~13.1k~~ | Flat round flasks came out as balls | the reader judges the depth; the spun shape is flattened to it, its label kept off it | `analyst/materials.py`, `Products.c` |
| ~~13.1l~~ | `start.bat` never rebuilt the Studio once built, nor set up the voice-over | it sets up the voice-over, brings the Studio up to date every run (seconds when nothing changed) and checks a new build | `start.bat` |

### 13.2 Left
| # | Flaw | Idea |
|---|---|---|
| 13.2a | Clear glass holding a liquid reads as one tinted solid (a decanter, Maison Héritage's perfume) | an inner liquid part inside a clear shell |
| 13.2b | A 3D model's product has no label (a label wraps only a spun shape) | the label laid on the model's front as a decal (built, then reverted for the freeze) |
| 13.2c | Gold print on white partly found (VELOURA read "V LOURA") | the logo box and the whole-word check for every product, not only glass |
| 13.2d | One voice for every ad | pace, pitch and expressiveness by the ad's mood |

---

## Risks and fallbacks

| Risk | Fallback |
|---|---|
| Rendering is slow (8 sub-frames × 450 frames × 3 ads) | Preview at 640x360 with 2 samples; final renders overnight; fewer samples if TAA already converges |
| Glass looks fake (no refraction) | Dark, frosted or opaque products; strong rim light sells the shape |
| Silhouette-to-profile fails on a photo | Category template profile, label still from the photo |
| Muse Spark tool calls are unreliable | Director emits the JSON shot plan; deterministic Python turns it into commands |
| Critic too lenient or too harsh | Measured checks carry the pass/fail; vision only adds issues; tune anchors on the eval set |
| API outage or credits run out on demo day | Disk cache + replay mode; all demo runs recorded by Nov 3 |
| Pre-existing engine ruled not allowed | Ask on day 1; if no, use it only as a library and show nothing of its features as new work |
| Real-time is too slow for the windowed view | The agents use the hidden renderer only; the window is for debugging |
| A downloaded model is wrong, broken or off-brand | Upload a .glb; or trace the product as round; demo only products whose model was checked |
| The network drops during a run (happened Oct 31) | Model calls wait out outages; re-run from cache (cached calls are free); 11.3a resume |
| The live director makes a poor film | It's experimental; the storyboard director is the default and the demo path |

## Cut list if behind

Cut in this order, top first (updated Oct 31):
1. World-space text, motion blur, voice brief, Muse Wonder
2. Phase 11 "later" items, then 11.2d props, 11.2c model choice by render
3. The live director in the demo (keep it in the repo, mention it)
4. 11.4 showcase items (show the run folder and the log instead)
5. Non-round products in the demo (keep the round ones: traced, with their real labels)

Never cut: the critic loop, the demo ads, the evaluation numbers, the README's
"built during the hackathon" section, the submission buffer on Nov 4.

---

## After the hackathon: the engine's module system

Saved for later. The text, timeline and product code written here become the first modules once the
engine has extension points. Short version of the plan:

- **M0 Safety net:** extend the engine's tests (`tests/world_tests.c`, `history_tests.c`,
  `serialize_tests.c`, `scene_file_tests.c`) to round-trip and undo every component;
  `docs/MODULES.md` design; build the engine from source in this repo (`PBR_ENGINE_SOURCE`).
- **M1 RHI gaps:** `R8`/`RG8`, `rhi_texture_update()`, several vertex streams, non-indexed and
  instanced draws, lines, scissor.
- **M2 Component registry:** `world_register_component()` with Reflect descriptions; generic storage;
  variable-size `entity_state` in History; Serialize and Commands by registry name; unknown
  components kept on save; 64-bit masks; entity events; Spin moved over as the proof.
- **M3 Frame phases and render hooks:** `systems_register(phase, fn)`; hooks for depth (all shadow
  passes, pre-pass, probes), opaque, transparent, overlay, screen; `scene_renderer_bind_lit_state()`.
- **M4 Asset types and `engine_module`:** `asset_type_register()`; module descriptor with
  dependencies on `App`; built-in extras (Spin, PlayerController, SceneTrigger, probes) as modules.
- **M5+:** move Timeline, Text and Products from this repo into modules; skeletal animation;
  physics, audio, particles, scripting as needed.
