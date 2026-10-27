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
//   camera.set         creates or moves a Camera entity and makes it the active one
//   timeline.*         keyframes (Timeline/TimelineCommands.c): set_track, add_key,
//                      remove_track, clear, get, seek, play, pause
//   shot.*             frames to PNG (Shot/ShotCommands.c): preview, render, bounds
//
// The timeline is saved and loaded with the scene, next to its file
// (scenes/<name>.timeline.json): the app calls studio_scene_file() from the
// command layer's on_scene_file.

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

// Once a frame, before world_update(): while the timeline plays, advances it
// by `dt` seconds (looping or stopping at the end) and writes it into the world.
void studio_update(studio* s, f32 dt);

// A scene was saved or loaded under `name` (cmd_scene_file_fn's arguments):
// saves the timeline next to it, or loads the one saved with it (none = empty).
void studio_scene_file(studio* s, cmd_scene_file_op op, const char* name);

// The settings a frame is rendered with: the defaults, then the environment
// (with the baked HDRI, if any), then the studio's own render settings.
// The window and shots both use it, so they show the same picture.
void studio_render_settings(const studio* s, scene_render_settings* out);

// The active Camera entity's view at `aspect`. False if there's none, or it
// was destroyed or lost its Camera since.
b8 studio_camera_view(const studio* s, f32 aspect, camera* out);

// Euler angles (World's Transform: degrees, yaw about Y then pitch about X,
// no roll) that turn an entity's -Z axis -- where a Camera looks -- along
// `direction`. False, and no change, if `direction` is (almost) zero.
b8 studio_look_rotation(const vec3 direction, vec3 out_rotation_deg);

// Every studio command (the timeline's included), for command_context.host_commands.
const cmd_host_command* studio_commands(uint32* out_count);
