# Architecture

How Studio turns a product photo and a brief into a finished ad: what each part does, what it hands to the next, and the rules that keep the result honest. For setup and results, see the [README](../README.md).

```
photo, brief ──► analyst ──► scout ──► stager ──► colourist ──► director ──► Studio ──► final cut
                 brand        3D model   up and     the photo's    storyboard   frames      video,
                 profile      (or traced) front     colours        (checked)                music
```

Two processes do the work:
- **The pipeline**, in Python (`pipeline/`): the agents, the Meta model clients, the catalogues and the final cut.
- **The Studio**, in C (`Engine/`, `Studio/main.c`): the renderer. It takes commands as JSON-RPC over WebSocket.

The pipeline starts a hidden Studio for each ad and drives it. Everything an ad does is written to its run folder.

## The run

`pipeline/runs.py`. Each ad is a run, `runs/<date>-<time>-ad-<photo>/`:

| File | What it holds |
|---|---|
| `inputs/` | The photo, the brief and options, and an uploaded model: enough to make it again (`--again`) |
| `log.jsonl` | Every event, timed: each model call with its cost, each Studio command, each decision with its reason |
| `masks.png`, `outline.png`, `label.png` | What SAM found, the traced shape, the unrolled label |
| `brand_profile.json` | The analyst's reading |
| `stage/`, `colour/` | The sheets Spark chose models, poses and colourings from |
| `product.glb`, `model_credit.json` | The fitted model and its licence credit |
| `drafts/draft_N.json` / `.png` | Each storyboard draft, its preview, and what the checks found |
| `storyboard.json` | The final plan |
| `final/` | The videos |
| `run.json` | The summary: status, time, model calls, cost, outputs |
| `traceback.txt` | Why it failed, if it did |

The app reads these files to show a run live or replayed. `scripts/evaluate.py` reads every run's log for the numbers in the README.

## The Meta models

`pipeline/meta/`. One client for the Meta Model API and Baseten (OpenAI-compatible):

| Model | Called by |
|---|---|
| **Muse Spark** (`muse-spark-1.3`) | Every judgment and plan (analyst, scout, stager, colourist, director, brief), with JSON-schema answers and vision |
| **Muse Spark Open** (Baseten) | The optional critic |
| **SAM 3.1** | The analyst's segmentation |
| **Muse Voice** | The spoken brief |
| **Muse Image** | The test photos |

How the client behaves:
- **Cached answers:** every answer is cached on disk by its request, so a rerun costs nothing.
- **Retries and outages:** rate limits and server errors are retried with backoff. A longer outage is waited out, up to about 10 minutes for Meta and 3 minutes for the catalogues, before the run fails.
- **Cost tracking:** every call's tokens and cost are logged in the run.

## 1. The brand analyst

`pipeline/agents/analyst/`. From the photo to a **brand profile** (`schemas/brand.py`).

1. **Segment** (`segment.py`). SAM 3.1 finds the product (by its category, else "product"), then its cap and its label. A part must lie mostly on the product and be cut to its mask. SAM also finds the caps and labels of things in the background.
2. **Palette** (`palette.py`). Each part's pixels are clustered in Lab colour space. Clusters of one hue form a family, and a family's colour is how it looks lit: its darkest clusters (shade) and near-white ones (specular highlights) are left out.
3. **Read** (`materials.py`). Muse Spark sees the photo with the masks. It reads the brand name, each part's material (colour, metallic, roughness, transmission, the colour of a liquid held in glass), the typography, the mood, and what the brand must avoid.
4. **Trace** (`profile.py`). The silhouette's half-width, row by row, becomes a profile `[radius, height]` per part, scaled to the product's real height. Spun round its axis, it is the 3D shape of a round product.
5. **Label** (`label.py`). The label is cut from the photo and unrolled: on a round body, a point at angle *a* shows at *x = axis + r·sin a*, so the photo is sampled back at even angles. The light across it is divided out, and it goes on the part its band lies on.
   - **No paper label:** with no label found, print on the body becomes the label, like a can's logo, an engraving or gold leaf. That means body pixels far from the body's own colour (big letters) or from their neighbourhood's (fine lines).
   - **Ignored:** slow shading, highlight stripes, specks and the cap's seam.
   - **The result** is a see-through decal over the body's material. Glass is skipped, since its refractions would pass for print.

If the photo shows no brand name, the brand comes from the brief (a word in capitals) or the photo's file name. If neither has one, the director is told never to invent one.

## 2. The scout

`pipeline/agents/scout.py`, `pipeline/catalog/`. A 3D model for a product that isn't round.

- **Shape.** Muse Spark judges from the photo whether the product is round from above, the same all the way round (a bottle, a jar, a can). If it is, it's traced (step 1). If not, Spark gives 2–3 searches, the most specific first.
- **Search.** Sketchfab, Objaverse (46,000 Sketchfab models via Hugging Face) and Poly Haven. Only **CC0 and CC-BY** models are kept, since repainting makes a derivative and an ad may be commercial; models over the face limit are skipped.
- **Pick by thumbnail.** Up to 12 thumbnails go on one numbered sheet, with their titles listed. Spark gives up to 3 finalists of the same kind of product and shape. It also lists every **branded** model (a logo, a brand name or lettering on it or in its title, or a specific real product like a named car), and those can't be finalists.
- **Audition.** The finalists are downloaded and rendered alike, each from three angles, in a column order hashed from their names so the first column isn't a hint. Spark picks the one standing in best and lists any whose renders show a brand. A branded choice gives way to the next unbranded finalist.
- **No model.** If the product isn't round and nothing usable is left, the ad stops with `NoModel`, asking for a model (`.glb`). Traced instead, a drone became a mushroom. Only if Spark can't judge the shape at all (an outage) is the product traced, as a round one would be.

Downloads are cached in `cache/models/`, each with a `.credit.json` that follows the model into the run.

## 3. The stager and the colourist

**The stager** (`stager.py`). A downloaded model can lie on its side or upside down, and its proportions can't tell up from down or front from back. Two sheets settle it:
1. **Which way is up:** the model standing each of the six ways up (A–F). Spark picks the one that stands like the photo's product.
2. **Which side faces the camera:** that pose seen every 45° (A–H). Spark picks the side the photo shows, which is turned to face the camera.

**Fitting** (`studio/models.py`):
- **Base stripped:** whatever the model came standing on (a coaster, a display stand, a patch of floor) is removed. That means thin, wide parts at its very bottom, found as connected pieces; the product's own flat bottom stays.
- **Normalised:** to the product's real height.
- **Glass:** a glass product is dressed in the analyst's materials.
- **Finish:** materials without a finish of their own get the photo's.

**The colourist** (`colourist.py`, `studio/recolour.py`). The model comes in its modeller's colours, so its textures are repainted in the photo's colours.
- **Two versions:** one pairs regions with colours by size, the other by lightness.
- **The choice:** Spark sees the photo next to the model as it is and both versions, and keeps the closest. It sometimes keeps the model's own colours.
- **The repaint itself:** works per material and per unique colour, in Lab, with glTF's linear colours converted properly.

## 4. The director

`pipeline/agents/director/`. The brief and the brand profile in, a **storyboard** (`schemas/storyboard.py`) out: the whole ad as data. Spark fills in a schema; code checks and builds it.

**What Spark is given** (`grammar.md`, generated from the schema by `grammar.py`): the shot grammar, every camera move and its arguments, the craft of short and long ads, and the **style library** (`styles.py`, 13 looks such as `luxury_dark`, `natural_organic`, `city_nights` and `summer_beach`). Each style has its set, lights, title, pace and moves. It's also given the set library: Poly Haven surfaces and light environments (`catalog/sets.py`), and props at their real sizes (`catalog/props.py`).

**What it plans:**
- **The look:**
  - the set: environment, backdrop or pedestal, and its surface;
  - the lights: one of 8 presets, with intensity and warmth;
  - the tonemapper (`aces` by default);
  - props, placed by angle and gap on the pedestal or the floor.
- **The shots:** each has one camera move:

  | Move | What the camera does |
  |---|---|
  | `static` | holds |
  | `orbit` | circles the product |
  | `dolly` | pushes in or pulls out |
  | `crane` | rises or drops |
  | `truck` | slides past |
  | `reveal` | pans onto the product |
  | `zoom` | changes the lens only |
  | `path` | glides through up to 8 waypoints on a monotone cubic, never swinging past one |

  A shot can add product motion (turn, float, drop, tilt), a shallow focus and a transition.
- **Titles,** an **end card**, and the **music**: its mood, tempo and key.
- **Length:** 15 s to 2 min. Ads over 30 s may hold shots up to 8 s and use up to 30 shots, built in parts: the mood, the product's details, the product in its world, the hero.

**The rules** (`write.py`), checked on every draft:
- **Hard rules:** a draft that breaks one goes back.
  - The shots add up to the length.
  - Each shot is 1.2–5 s (8 s past 30 s).
  - The last shot is a static hero from the front with the brand's name.
  - Titles enter late enough and stay long enough.
  - No jump cuts: each cut changes size, side or height enough.
  - A flat product is seen from above, and a thin one never edge-on.
  - Props don't float.
- **Taste rules:** these are told to Spark too, and a last draft that only breaks these is kept with warnings.
  - The product separates from its backdrop in tone.
  - Glass and metal have an environment to reflect.
  - A dark product isn't backlit into a silhouette.
  - Titles are measured readable against the rendered frame behind them.
  - Props hide at most 15% of the product.
  - A coloured product isn't greyed by `agx`.

Each draft is built in the Studio and previewed (`drafts/`). What's wrong goes back to Spark with its draft, up to 3 tries. Shot starts are then moved onto the music's beats (`encode/music.py: cut_to_beat`), within each shot's limits.

**Revisions** (`revise.py`) are made with tools that edit the storyboard: edit, add or remove a shot, a title or an animation track, or edit the look. Each edit is checked against the schema as it's made. The critic's fixes use them.

**The live director** (`live.py`, `--director live`) is an alternative: Spark drives the Studio command by command through tool calls, sees its frames and reviews its own film up to twice.

## 5. The Studio

`Engine/src/`, a C library on the prebuilt PBR engine (`Deps/`), and `Studio/main.c`.

| Module | What it does |
|---|---|
| `Studio/` | The command server (JSON-RPC 2.0 over WebSocket, a per-run token), studio commands, camera moves and framing, the 8 lighting presets |
| `Products/` | Products spun from profiles, labels wrapped round a part's band, backdrops and pedestals; all as glTF |
| `Timeline/` | Keyframed tracks on any component field, with easing; the camera moves are keys on it |
| `Text/` | Titles with signed-distance-field fonts and kerning, sized as a share of the frame's height |
| `Shot/` | Offscreen rendering: PNGs at given times, or a time range straight into an mp4 through ffmpeg; where an entity is in the frame (`shot.bounds`) |

**Framing:** `fill` is the subject's share of the frame's height, as seen from the camera's elevation, so a jar and a bottle frame alike. The Studio computes the distance for each frame.

**Rendering:**
- **Repeatable frames:** each frame is rendered from scratch at its time, so a frame is the same alone or in a sequence.
- **Samples:** 8 per frame, which matches 16 to within 54 dB.
- **Motion blur:** the final render uses a 180° shutter, spreading those samples across the shutter's time and averaging them. That costs about a third more time.
- **Speed:** a 1080p frame takes about 0.5 s on an Intel Iris Xe.

`studio/build.py` turns a storyboard into Studio commands: the set, the product (traced or a model), props, lights, camera keys, product motion and titles.

## 6. The final cut

`pipeline/studio/render.py`, `pipeline/encode/`.

- **Render.** The storyboard is rendered to `final/raw.mp4`, fading in from black and out.
- **Music** (`music.py`): synthesized note by note in the planned mood (dark, calm, energetic, warm), tempo and key.
  - **The mix:** pads, a plucked or electric-piano part, a bass and drums. A swell lands on the hero shot's first beat.
  - **The sound:** a synthesized stereo room (convolution reverb), the kick pumping the pads, soft saturation.
  - **Mastering:** to -16 LUFS (BS.1770), peaks at -1 dB.
  - **Licensed music:** a track at `Assets/music/<mood>.mp3` is used instead.
- **End card** (`endcard.py`): the product's photo, cut out (the analyst's packshot), on a calm colour, with the brand's name in the titles' font and a short line under it.
- **Finish** (`finish.py`): H.264 and AAC.
- **A second frame** (`studio/reframe.py`): 9:16 from a 16:9 plan, or the reverse.
  - **Titles:** refitted to the new width.
  - **A wide product in a narrow frame:** each shot is measured, and all the shots' fills are scaled by one factor so the widest spans 68% of the width. Close-ups keep their crop.

## The critic (optional)

`pipeline/agents/critic/`, `--critic`. Before the final render, the ad is judged and revised.

1. **Measure** (`measure.py`, `cuts.py`). Each frame is rendered three ways: as is, without the product's shadow, without the product. The difference gives the product's exact pixels, from which the critic measures:
   - its fill and which edges cut it;
   - outline lost in the background;
   - blown highlights and crushed shadows;
   - distance from the brand's colours;
   - titles over it.

   At each cut, the Studio reports how far the camera turns and whether the lights change.
2. **Judge** (`judge.py`, `whole.py`). Muse Spark Open sees each shot's frames with those numbers, and scores six categories from 0 to 10 against written anchors. A second pass judges the whole ad.
   - **Bound to the numbers:** a major measured fault must appear in the critique, scored 6 or less, or the answer goes back.
   - **Passing:** decided in code: every score at least 7 and no major issue. Near the mark, a shot is judged twice and the worse result kept.
3. **Revise** (`loop.py`). The critic's fixes, written as storyboard edits, are applied by the director's tools. The ad is rebuilt and judged again, up to 3 times, and the best round is kept.

## The app

`app/server.py` (FastAPI) and `app/static/index.html` (one page).
- **Jobs:** queued and made one at a time by the same producer as the command line.
- **The page** follows a run through Server-Sent Events built from its log:
  - progress with time left;
  - the brand profile;
  - the model and its credit;
  - each draft with its problems and changes;
  - **How Spark decided:** every choice in order with the sheet behind it;
  - the videos.
- **Runs:** can be cancelled, made again or replayed at their real pace. Finished ads collect in the gallery.
- **The spoken brief:** recorded in the page, transcribed by Muse Voice, then mended by Muse Spark (`agents/brief.py`), which corrects only what the ear got wrong.

## Tests

`tests/`, run with `python -m unittest discover -s tests -t .`: 53 tests, no GPU or network. Each guards something that went wrong once:
- music cut off the beat;
- props placed off the pedestal;
- a coaster left under a mug, and a stand in two pieces;
- a recolour pairing colours wrongly;
- a run's log broken by a half-written line;
- outages;
- path framing;
- a label past its part, and print versus shading;
- highlights in the palette;
- the scout guessing a shape;
- an invented brand, and honey turning black in glass.

`ctest` runs the Studio's timeline and text layout tests.
