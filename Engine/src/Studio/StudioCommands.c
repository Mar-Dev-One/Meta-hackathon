// The studio's host commands (Studio.h). Each one validates every argument
// before it changes anything, so a failed command leaves the studio as it was.

#include "Studio.h"

#include "CameraMoves.h"
#include "Common/Json.h"
#include "LightingCommands.h"
#include "Products/ProductCommands.h"
#include "Shot/ShotCommands.h"
#include "Text/TextCommands.h"
#include "Timeline/TimelineCommands.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>


static void
add_vec3(cJSON* object, const char* name, const vec3 v)
{
    json_add_floats(object, name, v, 3);
}

// --- studio.reset ------------------------------------------------------------------

static b8
cmd_studio_reset(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)out_result; (void)error; (void)error_size;
    studio_reset((studio*)user);
    return true;
}

// --- environment.get / environment.set ---------------------------------------------

static b8
cmd_environment_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    *out_result = serialize_environment(((studio*)user)->env);
    return true;
}

static b8
cmd_environment_set(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;
    if (!deserialize_environment(args, s->env, error, error_size))
        return false;
    *out_result = serialize_environment(s->env);
    return true;
}

// --- render.get / render.set ---------------------------------------------------------

static b8
cmd_render_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    *out_result = studio_render_to_json((studio*)user);
    return true;
}

static b8
cmd_render_set(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;
    if (!studio_render_from_json(s, args, error, error_size))
        return false;
    *out_result = studio_render_to_json(s);
    return true;
}

// --- camera.get / camera.set -------------------------------------------------------

static cJSON*
describe_camera(const studio* s)
{
    cJSON*    result = cJSON_CreateObject();
    entity_id e      = s->active_camera[0] ? world_find(s->w, s->active_camera) : ENTITY_NULL;
    c_camera* cam    = e ? world_camera(s->w, e) : NULL;
    if (!cam)
    {
        cJSON_AddNullToObject(result, "camera");
        return result;
    }

    const c_transform* t = world_transform(s->w, e);
    cJSON_AddStringToObject(result, "camera", world_name(s->w, e));
    add_vec3(result, "position", t->position);
    add_vec3(result, "rotation_deg", t->rotation_deg);
    cJSON_AddNumberToObject(result, "fov_degrees", json_round6(cam->fov_degrees));
    cJSON_AddNumberToObject(result, "near_plane", json_round6(cam->near_plane));
    cJSON_AddNumberToObject(result, "far_plane", json_round6(cam->far_plane));
    if (s->look_at[0])
        cJSON_AddStringToObject(result, "look_at", s->look_at);
    else
        cJSON_AddNullToObject(result, "look_at");
    return result;
}

static b8
cmd_camera_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    *out_result = describe_camera((studio*)user);
    return true;
}

static b8
cmd_camera_set(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;
    world*  w = s->w;

    const char*  name       = STUDIO_DEFAULT_CAMERA;
    const cJSON* entity_arg = cJSON_GetObjectItemCaseSensitive(args, "entity");
    if (entity_arg)
    {
        if (!cJSON_IsString(entity_arg) || !entity_arg->valuestring[0] || strlen(entity_arg->valuestring) >= ENTITY_NAME_MAX)
            return set_error(error, error_size, "\"entity\" must be a name of 1 to %d characters", ENTITY_NAME_MAX - 1);
        name = entity_arg->valuestring;
    }

    vec3 position = { 0.0f, 0.0f, 0.0f };
    vec3 target;
    f32  fov = STUDIO_DEFAULT_FOV, near_plane = STUDIO_DEFAULT_NEAR, far_plane = STUDIO_DEFAULT_FAR;
    int  has_position = arg_vec3(args, "position", position, error, error_size);
    int  has_target   = arg_vec3(args, "target", target, error, error_size);
    // The ranges are the Camera component's own (World/Reflect.h), so camera.set and component.set agree.
    int  has_fov      = arg_number(args, "fov_degrees", 1.0f, 179.0f, &fov, error, error_size);
    int  has_near     = arg_number(args, "near_plane", 0.001f, 100.0f, &near_plane, error, error_size);
    int  has_far      = arg_number(args, "far_plane", 0.01f, 100000.0f, &far_plane, error, error_size);
    if (has_position < 0 || has_target < 0 || has_fov < 0 || has_near < 0 || has_far < 0)
        return false;

    entity_id e   = world_find(w, name);
    c_camera* cam = e ? world_camera(w, e) : NULL;
    if (!e && !has_position)
        return set_error(error, error_size, "there's no entity \"%s\" yet: give a \"position\" to create the camera there", name);

    // Unset clip planes keep the camera's own, so check the pair it will end up with.
    if (cam && !has_near) near_plane = cam->near_plane;
    if (cam && !has_far)  far_plane  = cam->far_plane;
    if (near_plane >= far_plane)
        return set_error(error, error_size, "\"near_plane\" (%g) must be less than \"far_plane\" (%g)", near_plane, far_plane);

    if (e && !has_position)
        glm_vec3_copy(world_transform(w, e)->position, position);

    vec3 rotation = { 0.0f, 0.0f, 0.0f };
    if (has_target)
    {
        vec3 direction;
        glm_vec3_sub(target, position, direction);
        if (!studio_look_rotation(direction, rotation))
            return set_error(error, error_size, "\"target\" is where the camera is: it needs a point to look at");
    }

    // Valid: make the changes.
    e   = studio_camera_entity(s, name);
    cam = world_camera(w, e);
    if (has_fov)
        cam->fov_degrees = fov;
    cam->near_plane  = near_plane;
    cam->far_plane   = far_plane;

    c_transform* t = world_transform(w, e);
    glm_vec3_copy(position, t->position);
    if (has_target)
        glm_vec3_copy(rotation, t->rotation_deg);

    // Aimed once, here: no longer kept on a look-at entity.
    snprintf(s->active_camera, sizeof(s->active_camera), "%s", world_name(w, e));
    s->look_at[0] = '\0';
    *out_result = describe_camera(s);
    return true;
}

// --- Table ----------------------------------------------------------------------------

static const cmd_arg ENVIRONMENT_ARGS[] = {
    { "hdri", "string", false, "Radiance .hdr under assets/ (e.g. \"hdri/studio_small.hdr\"); \"\" = none" },
    { "use_ibl", "boolean", false, "light the scene with the HDRI" },
    { "show_skybox", "boolean", false, "draw the HDRI as the background" },
    { "sky_blur", "number", false, "0 (sharp) .. 1 (blurriest) background" },
    { "ambient_strength", "number", false, "0 .. 4" },
    { "exposure", "number", false, "(0, 16]" },
    { "auto_exposure", "boolean", false, "adapt to the scene's brightness; keep false for repeatable frames" },
    { "bloom", "number", false, "0 (none) .. 1" },
    { "tonemap", "string", false, "\"aces\", \"agx\" or \"neutral\"" },
    { "ssao", "boolean", false, "ambient occlusion in creases and contacts" },
    { "ssao_radius", "number", false, "0.05 .. 5 meters" },
};

static const cmd_arg RENDER_ARGS[] = {
    { "antialiasing", "string", false, "\"off\", \"fxaa\" or \"taa\"" },
    { "shadows", "boolean", false, "shadows from the sun, spot and point lights" },
    { "clear_color", "vec3", false, "linear RGB background where nothing is drawn and there's no skybox" },
};

static const cmd_arg CAMERA_SET_ARGS[] = {
    { "entity", "string", false, "the Camera entity's name (default \"" STUDIO_DEFAULT_CAMERA "\"); created if missing" },
    { "position", "vec3", false, "where the camera is, in meters; required when creating it" },
    { "target", "vec3", false, "a point to look at; without it the rotation is kept" },
    { "fov_degrees", "number", false, "vertical field of view, 1 .. 179 (new cameras: 30)" },
    { "near_plane", "number", false, "meters" },
    { "far_plane", "number", false, "meters" },
};

static const cmd_host_command STUDIO_COMMANDS[] = {
    { "studio.reset", "Empties the stage: destroys every entity and timeline track, and resets the environment, render settings and active camera.",
      NULL, 0, true, cmd_studio_reset },
    { "environment.get", "The environment: HDRI, image-based lighting, exposure, bloom, tone mapping, SSAO.",
      NULL, 0, false, cmd_environment_get },
    { "environment.set", "Sets any of the environment's keys; the others keep their values. A new HDRI is baked before the next frame.",
      ENVIRONMENT_ARGS, sizeof(ENVIRONMENT_ARGS) / sizeof(ENVIRONMENT_ARGS[0]), false, cmd_environment_set },
    { "render.get", "Render settings that aren't part of the environment.",
      NULL, 0, false, cmd_render_get },
    { "render.set", "Sets any of the render settings; the others keep their values.",
      RENDER_ARGS, sizeof(RENDER_ARGS) / sizeof(RENDER_ARGS[0]), false, cmd_render_set },
    { "camera.get", "The active camera (the one the frame is seen through), or {\"camera\": null}.",
      NULL, 0, false, cmd_camera_get },
    { "camera.set", "Creates or moves a Camera entity, aims it at a target once (turning off camera.move's look-at) and makes it the active camera.",
      CAMERA_SET_ARGS, sizeof(CAMERA_SET_ARGS) / sizeof(CAMERA_SET_ARGS[0]), true, cmd_camera_set },
};

const cmd_host_command*
studio_commands(uint32* out_count)
{
    // The studio's own commands, then each part's, in one table (the
    // command layer takes one), built on first use.
    static cmd_host_command* all;
    static uint32            all_count;
    if (!all)
    {
        enum { TABLES = 7 };
        uint32                  counts[TABLES] = { sizeof(STUDIO_COMMANDS) / sizeof(STUDIO_COMMANDS[0]) };
        const cmd_host_command* tables[TABLES] = { STUDIO_COMMANDS, camera_move_commands(&counts[1]),
                                                   lighting_commands(&counts[2]), product_commands(&counts[3]),
                                                   text_commands(&counts[4]), timeline_commands(&counts[5]),
                                                   shot_commands(&counts[6]) };
        uint32 total = 0;
        for (int i = 0; i < TABLES; ++i)
            total += counts[i];

        all = malloc(total * sizeof(*all));
        for (int i = 0; i < TABLES; ++i)
        {
            memcpy(all + all_count, tables[i], counts[i] * sizeof(*all));
            all_count += counts[i];
        }
    }
    *out_count = all_count;
    return all;
}
