#pragma once

#include "Commands/Commands.h"
#include "Core/Defines.h"
#include "Renderer/IBL.h"
#include "Renderer/SceneRenderer.h"
#include "Scene/Camera.h"
#include "Shot/Shot.h"
#include "Timeline/Timeline.h"
#include "World/Environment.h"
#include "World/World.h"

// The studio: what a shot is set up with, on top of the engine's World --
// the environment (HDRI, exposure, tone mapping), the render settings the
// environment doesn't hold, which Camera entity the frame is seen through,
// and the timeline that animates it all. Agents drive it with the commands
// below, which the app installs as its host commands
// (command_context.host_commands = studio_commands(), host_user = the studio):
//
//   studio.reset       empty stage: no entities or tracks, default environment and settings
//   environment.get    the environment, in World/Environment.h's JSON
//   environment.set    any of its keys; the app bakes a new HDRI on the next frame
//   render.get         antialiasing, shadows, clear_color
//   render.set         any of them
//   camera.get         the active camera, or null
//   camera.set         creates or moves a Camera entity, aims it once, makes it the active one
//   camera.move        a shot's camera move: keys for an orbit, dolly, crane, ...
//                      around a subject (Studio/CameraMoves.c)
//   lighting.preset    a studio lighting setup around a subject (Studio/Lighting.c)
//   product.create     a product model spun from a profile, with a label (Products/Products.c)
//   backdrop.create    a cyclorama or a round pedestal (Products/Products.c)
//   timeline.*         keyframes (Timeline/TimelineCommands.c): set_track, add_key,
//                      remove_track, clear, get, seek, play, pause
//   shot.*             frames to PNG or video (Shot/ShotCommands.c): preview, render, bounds
//
// Look-at: the active camera can be kept aimed at an entity (`look_at`, set
// by camera.move to "<camera>_target"). After the timeline is written,
// studio_evaluate() turns the camera towards it, so keyframing the target's
// position moves where the camera looks.
//
// The studio's state beyond the World -- the timeline, the active camera and
// look-at, the render settings -- is saved and loaded with the scene, next to
// its file (scenes/<name>.studio.json): the app calls studio_scene_file()
// from the command layer's on_scene_file.

#define STUDIO_DEFAULT_CAMERA "camera"

// A Camera entity made by camera.set without a field of view gets this:
// vertical degrees, about a 50 mm lens on full frame -- a product lens.
#define STUDIO_DEFAULT_FOV  30.0f
#define STUDIO_DEFAULT_NEAR 0.05f
#define STUDIO_DEFAULT_FAR  100.0f

typedef struct studio
{
    world*             w;     // borrowed
    scene_environment* env;   // borrowed
    ibl_cache*         ibl;   // borrowed, may be NULL: env->hdri baked (the app syncs it each frame; shots before rendering)

    // Render settings that aren't part of the environment.
    scene_antialiasing antialiasing;
    b8                 shadows;
    vec3               clear_color;   // linear HDR background where nothing is drawn and there's no skybox

    // The Camera entity the frame is seen through, by name (so it survives
    // undo and scene loads); "" = the app's own camera.
    char active_camera[ENTITY_NAME_MAX];

    // The entity the active camera is kept aimed at; "" = none (it keeps
    // its own rotation).
    char look_at[ENTITY_NAME_MAX];

    timeline      timeline;
    shot_renderer shots;   // made on the first shot.* render; needs the GL context
} studio;

// `w`, `env` and `ibl` (may be NULL) must outlive the studio. Starts with
// the default render settings, no active camera and an empty timeline;
// leaves the world and environment as they are.
void studio_init(studio* s, world* w, scene_environment* env, ibl_cache* ibl);
void studio_destroy(studio* s);   // while the GL context is still alive

// An empty stage: destroys every entity and track, and puts the environment
// and the render settings back to their defaults, with no active camera.
void studio_reset(studio* s);

// The scene at time `t`: writes the timeline into the world, aims the active
// camera at its look-at entity, and updates the world's matrices. Every
// part of the studio shows a time through this. Returns how many tracks
// were written; *out_skipped (may be NULL) gets those whose entity is missing.
uint32 studio_evaluate(studio* s, f32 t, uint32* out_skipped);

// Once a frame: while the timeline plays, advances it by `dt` seconds
// (looping or stopping at the end) and shows the scene then.
void studio_update(studio* s, f32 dt);

// A scene was saved or loaded under `name` (cmd_scene_file_fn's arguments):
// saves the studio's state next to it, or loads the one saved with it (none =
// an empty timeline and no camera; render settings as they are).
void studio_scene_file(studio* s, cmd_scene_file_op op, const char* name);

// The studio's state beyond the World as JSON: { "camera", "look_at",
// "render": {...}, "timeline": {...} }. studio_from_json() reads it back,
// all-or-nothing.
cJSON* studio_to_json(const studio* s);
b8     studio_from_json(studio* s, const cJSON* json, char* error, size_t error_size);

// The render settings as JSON ({ "antialiasing", "shadows", "clear_color" }),
// and back: only the keys present, all-or-nothing.
cJSON* studio_render_to_json(const studio* s);
b8     studio_render_from_json(studio* s, const cJSON* json, char* error, size_t error_size);

// The settings a frame is rendered with: the defaults, then the environment
// (with the baked HDRI, if any), then the studio's own render settings.
// The window and shots both use it, so they show the same picture.
void studio_render_settings(const studio* s, scene_render_settings* out);

// The entity called `name` with a Camera, creating either if missing
// (STUDIO_DEFAULT_FOV, _NEAR, _FAR); it isn't made the active camera.
entity_id studio_camera_entity(studio* s, const char* name);

// The active Camera entity's view at `aspect`. False if there's none, or it
// was destroyed or lost its Camera since.
b8 studio_camera_view(const studio* s, f32 aspect, camera* out);

// Euler angles (World's Transform: degrees, yaw about Y then pitch about X,
// no roll) that turn an entity's -Z axis -- where a Camera looks -- along
// `direction`. False, and no change, if `direction` is (almost) zero.
b8 studio_look_rotation(const vec3 direction, vec3 out_rotation_deg);

// Every studio command (the timeline's, shots' and camera moves' included),
// for command_context.host_commands.
const cmd_host_command* studio_commands(uint32* out_count);
