#pragma once

#include "Commands/Commands.h"
#include "Core/Defines.h"
#include "Renderer/SceneRenderer.h"
#include "Scene/Camera.h"
#include "World/Environment.h"
#include "World/World.h"

// The studio: what a shot is set up with, on top of the engine's World --
// the environment (HDRI, exposure, tone mapping), the render settings the
// environment doesn't hold, and which Camera entity the frame is seen
// through. Agents drive it with the commands below, which the app installs
// as its host commands (command_context.host_commands, host_user = the
// studio):
//
//   studio.reset       empty stage: no entities, default environment and settings
//   environment.get    the environment, in World/Environment.h's JSON
//   environment.set    any of its keys; the app bakes a new HDRI on the next frame
//   render.get         antialiasing, shadows, clear_color
//   render.set         any of them
//   camera.get         the active camera, or null
//   camera.set         creates or moves a Camera entity and makes it the active one

#define STUDIO_DEFAULT_CAMERA "camera"

// A Camera entity made by camera.set without a field of view gets this:
// vertical degrees, about a 50 mm lens on full frame -- a product lens.
#define STUDIO_DEFAULT_FOV  30.0f
#define STUDIO_DEFAULT_NEAR 0.05f
#define STUDIO_DEFAULT_FAR  100.0f

typedef struct studio
{
    world*             w;     // borrowed
    scene_environment* env;   // borrowed; the app bakes env->hdri (ibl_cache_sync())

    // Render settings that aren't part of the environment.
    scene_antialiasing antialiasing;
    b8                 shadows;
    vec3               clear_color;   // linear HDR background where nothing is drawn and there's no skybox

    // The Camera entity the frame is seen through, by name (so it survives
    // undo and scene loads); "" = the app's own camera.
    char active_camera[ENTITY_NAME_MAX];
} studio;

// `w` and `env` must outlive the studio. Starts with the default render
// settings and no active camera; leaves the world and environment as they are.
void studio_init(studio* s, world* w, scene_environment* env);

// An empty stage: destroys every entity, and puts the environment and the
// render settings back to their defaults, with no active camera.
void studio_reset(studio* s);

// Writes the studio's render settings into `settings` -- call after
// scene_render_settings_apply_environment().
void studio_apply_render_settings(const studio* s, scene_render_settings* settings);

// The active Camera entity's view at `aspect`. False if there's none, or it
// was destroyed or lost its Camera since.
b8 studio_camera_view(const studio* s, f32 aspect, camera* out);

// Euler angles (World's Transform: degrees, yaw about Y then pitch about X,
// no roll) that turn an entity's -Z axis -- where a Camera looks -- along
// `direction`. False, and no change, if `direction` is (almost) zero.
b8 studio_look_rotation(const vec3 direction, vec3 out_rotation_deg);

// The studio's commands, for command_context.host_commands.
const cmd_host_command* studio_commands(uint32* out_count);
