// The studio's host commands (Studio.h). Each one validates every argument
// before it changes anything, so a failed command leaves the studio as it was.

#include "Studio.h"

#include "Timeline/TimelineCommands.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// --- Arguments -------------------------------------------------------------------

static b8
fail(char* error, size_t error_size, const char* format, ...)
{
    va_list args;
    va_start(args, format);
    vsnprintf(error, error_size, format, args);
    va_end(args);
    return false;
}

// 1 if `name` is in `args` and valid, 0 if absent, -1 (error filled) if invalid.
static int
read_number(const cJSON* args, const char* name, f32 min, f32 max, f32* out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!cJSON_IsNumber(item) || item->valuedouble < min || item->valuedouble > max)
    {
        fail(error, error_size, "\"%s\" must be a number from %g to %g", name, min, max);
        return -1;
    }
    *out = (f32)item->valuedouble;
    return 1;
}

static int
read_vec3(const cJSON* args, const char* name, vec3 out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;

    b8 ok = cJSON_IsArray(item) && cJSON_GetArraySize(item) == 3;
    for (int i = 0; ok && i < 3; ++i)
    {
        const cJSON* v = cJSON_GetArrayItem(item, i);
        ok = cJSON_IsNumber(v) && isfinite(v->valuedouble);
        if (ok)
            out[i] = (f32)v->valuedouble;
    }
    if (!ok)
    {
        fail(error, error_size, "\"%s\" must be an array of three numbers, e.g. [0, 1.5, 3]", name);
        return -1;
    }
    return 1;
}

static int
read_bool(const cJSON* args, const char* name, b8* out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!cJSON_IsBool(item))
    {
        fail(error, error_size, "\"%s\" must be true or false", name);
        return -1;
    }
    *out = cJSON_IsTrue(item);
    return 1;
}

static f64
round6(f32 value)
{
    return round((f64)value * 1e6) / 1e6;
}

static void
add_vec3(cJSON* object, const char* name, const vec3 v)
{
    cJSON* array = cJSON_AddArrayToObject(object, name);
    for (int i = 0; i < 3; ++i)
        cJSON_AddItemToArray(array, cJSON_CreateNumber(round6(v[i])));
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

static cJSON*
describe_render(const studio* s)
{
    cJSON* result = cJSON_CreateObject();
    cJSON_AddStringToObject(result, "antialiasing", scene_antialiasing_name(s->antialiasing));
    cJSON_AddBoolToObject(result, "shadows", s->shadows);
    add_vec3(result, "clear_color", s->clear_color);
    return result;
}

static b8
cmd_render_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    *out_result = describe_render((studio*)user);
    return true;
}

static b8
cmd_render_set(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    scene_antialiasing aa = s->antialiasing;
    const cJSON* aa_arg = cJSON_GetObjectItemCaseSensitive(args, "antialiasing");
    if (aa_arg && (!cJSON_IsString(aa_arg) || !scene_antialiasing_from_name(aa_arg->valuestring, &aa)))
        return fail(error, error_size, "\"antialiasing\" must be \"off\", \"fxaa\" or \"taa\"");

    b8   shadows = s->shadows;
    vec3 clear_color;
    glm_vec3_copy(s->clear_color, clear_color);
    if (read_bool(args, "shadows", &shadows, error, error_size) < 0
        || read_vec3(args, "clear_color", clear_color, error, error_size) < 0)
        return false;
    if (clear_color[0] < 0.0f || clear_color[1] < 0.0f || clear_color[2] < 0.0f)
        return fail(error, error_size, "\"clear_color\" is linear RGB and can't be negative");

    s->antialiasing = aa;
    s->shadows      = shadows;
    glm_vec3_copy(clear_color, s->clear_color);
    *out_result = describe_render(s);
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
    cJSON_AddNumberToObject(result, "fov_degrees", round6(cam->fov_degrees));
    cJSON_AddNumberToObject(result, "near_plane", round6(cam->near_plane));
    cJSON_AddNumberToObject(result, "far_plane", round6(cam->far_plane));
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
            return fail(error, error_size, "\"entity\" must be a name of 1 to %d characters", ENTITY_NAME_MAX - 1);
        name = entity_arg->valuestring;
    }

    vec3 position = { 0.0f, 0.0f, 0.0f };
    vec3 target;
    f32  fov = STUDIO_DEFAULT_FOV, near_plane = STUDIO_DEFAULT_NEAR, far_plane = STUDIO_DEFAULT_FAR;
    int  has_position = read_vec3(args, "position", position, error, error_size);
    int  has_target   = read_vec3(args, "target", target, error, error_size);
    int  has_fov      = read_number(args, "fov_degrees", 1.0f, 170.0f, &fov, error, error_size);
    int  has_near     = read_number(args, "near_plane", 0.001f, 1000.0f, &near_plane, error, error_size);
    int  has_far      = read_number(args, "far_plane", 0.01f, 100000.0f, &far_plane, error, error_size);
    if (has_position < 0 || has_target < 0 || has_fov < 0 || has_near < 0 || has_far < 0)
        return false;

    entity_id e   = world_find(w, name);
    c_camera* cam = e ? world_camera(w, e) : NULL;
    if (!e && !has_position)
        return fail(error, error_size, "there's no entity \"%s\" yet: give a \"position\" to create the camera there", name);

    // Unset clip planes keep the camera's own, so check the pair it will end up with.
    if (cam && !has_near) near_plane = cam->near_plane;
    if (cam && !has_far)  far_plane  = cam->far_plane;
    if (near_plane >= far_plane)
        return fail(error, error_size, "\"near_plane\" (%g) must be less than \"far_plane\" (%g)", near_plane, far_plane);

    if (e && !has_position)
        glm_vec3_copy(world_transform(w, e)->position, position);

    vec3 rotation = { 0.0f, 0.0f, 0.0f };
    if (has_target)
    {
        vec3 direction;
        glm_vec3_sub(target, position, direction);
        if (!studio_look_rotation(direction, rotation))
            return fail(error, error_size, "\"target\" is where the camera is: it needs a point to look at");
    }

    // Valid: make the changes.
    if (!e)
        e = world_create(w, name);   // the name is free, so it's kept as given
    if (!cam)
        cam = world_add_camera(w, e, fov, near_plane, far_plane);
    if (has_fov)
        cam->fov_degrees = fov;
    cam->near_plane  = near_plane;
    cam->far_plane   = far_plane;

    c_transform* t = world_transform(w, e);
    glm_vec3_copy(position, t->position);
    if (has_target)
        glm_vec3_copy(rotation, t->rotation_deg);

    snprintf(s->active_camera, sizeof(s->active_camera), "%s", world_name(w, e));
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
    { "fov_degrees", "number", false, "vertical field of view, 1 .. 170 (new cameras: 30)" },
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
    { "camera.set", "Creates or moves a Camera entity, aims it at a target and makes it the active camera.",
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
        uint32                  timeline_count;
        const cmd_host_command* timeline     = timeline_commands(&timeline_count);
        uint32                  studio_count = sizeof(STUDIO_COMMANDS) / sizeof(STUDIO_COMMANDS[0]);

        all = malloc((studio_count + timeline_count) * sizeof(*all));
        memcpy(all, STUDIO_COMMANDS, sizeof(STUDIO_COMMANDS));
        memcpy(all + studio_count, timeline, timeline_count * sizeof(*all));
        all_count = studio_count + timeline_count;
    }
    *out_count = all_count;
    return all;
}
