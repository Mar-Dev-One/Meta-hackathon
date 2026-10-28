#include "Studio.h"

#include "Common/Json.h"
#include "Core/FileIO.h"
#include "Core/Paths.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RAD_TO_DEG (180.0f / 3.14159265358979f)

static void
reset_render_settings(studio* s)
{
    scene_render_settings defaults = scene_render_settings_default();
    s->antialiasing = SCENE_AA_TAA;   // a product shot holds still long enough for TAA to settle
    s->shadows      = defaults.shadows;
    glm_vec3_copy(defaults.clear_color, s->clear_color);
}

void
studio_init(studio* s, world* w, scene_environment* env, ibl_cache* ibl)
{
    memset(s, 0, sizeof(*s));
    s->w   = w;
    s->env = env;
    s->ibl = ibl;
    reset_render_settings(s);
    timeline_init(&s->timeline);
    text_layer_init(&s->texts);
    // Titles animate on the timeline as component "Text".
    s->timeline.custom = (timeline_custom_target){ "Text", &s->texts, text_track_describe, text_track_write };
}

void
studio_destroy(studio* s)
{
    text_layer_destroy(&s->texts);
    shot_renderer_destroy(&s->shots);
    timeline_destroy(&s->timeline);
}

void
studio_reset(studio* s)
{
    world_clear(s->w);
    *s->env = scene_environment_default();
    reset_render_settings(s);
    s->active_camera[0] = '\0';
    s->look_at[0]       = '\0';
    timeline_clear(&s->timeline);
    text_layer_clear(&s->texts);
}

// --- Evaluation -----------------------------------------------------------------------

// Turns the active camera towards its look-at entity, from their world
// positions as of the last world_update(). False if either is missing.
static b8
aim_camera(studio* s)
{
    if (!s->look_at[0] || !s->active_camera[0])
        return false;
    entity_id cam    = world_find(s->w, s->active_camera);
    entity_id target = world_find(s->w, s->look_at);
    const vec4* cam_matrix    = cam ? world_matrix(s->w, cam) : NULL;
    const vec4* target_matrix = target ? world_matrix(s->w, target) : NULL;
    if (!cam_matrix || !target_matrix)
        return false;

    vec3 direction;
    glm_vec3_sub((f32*)target_matrix[3], (f32*)cam_matrix[3], direction);
    return studio_look_rotation(direction, world_transform(s->w, cam)->rotation_deg);
}

uint32
studio_evaluate(studio* s, f32 t, uint32* out_skipped)
{
    uint32 written = timeline_evaluate(&s->timeline, s->w, t, out_skipped);
    world_update(s->w);
    if (aim_camera(s))
        world_update(s->w);   // the camera's new rotation into its matrix
    return written;
}

void
studio_update(studio* s, f32 dt)
{
    timeline* tl = &s->timeline;
    if (!tl->playing)
        return;

    f32 duration = timeline_duration(tl);
    f32 t        = tl->time + dt;
    if (t >= duration)
    {
        if (tl->loop && duration > 0.0f)
            t = fmodf(t, duration);
        else
        {
            t           = duration;
            tl->playing = false;
        }
    }
    studio_evaluate(s, t, NULL);
}

// --- Saving with the scene ---------------------------------------------------------------

cJSON*
studio_render_to_json(const studio* s)
{
    cJSON* json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "antialiasing", scene_antialiasing_name(s->antialiasing));
    cJSON_AddBoolToObject(json, "shadows", s->shadows);
    json_add_floats(json, "clear_color", s->clear_color, 3);
    return json;
}

b8
studio_render_from_json(studio* s, const cJSON* json, char* error, size_t error_size)
{
    scene_antialiasing aa = s->antialiasing;
    const cJSON* aa_json  = cJSON_GetObjectItemCaseSensitive(json, "antialiasing");
    if (aa_json && (!cJSON_IsString(aa_json) || !scene_antialiasing_from_name(aa_json->valuestring, &aa)))
        return set_error(error, error_size, "\"antialiasing\" must be \"off\", \"fxaa\" or \"taa\"");

    b8   shadows = s->shadows;
    vec3 clear_color;
    glm_vec3_copy(s->clear_color, clear_color);
    if (arg_bool(json, "shadows", &shadows, error, error_size) < 0
        || arg_vec3(json, "clear_color", clear_color, error, error_size) < 0)
        return false;
    if (clear_color[0] < 0.0f || clear_color[1] < 0.0f || clear_color[2] < 0.0f)
        return set_error(error, error_size, "\"clear_color\" is linear RGB and can't be negative");

    s->antialiasing = aa;
    s->shadows      = shadows;
    glm_vec3_copy(clear_color, s->clear_color);
    return true;
}

cJSON*
studio_to_json(const studio* s)
{
    cJSON* json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "camera", s->active_camera);
    cJSON_AddStringToObject(json, "look_at", s->look_at);
    cJSON_AddItemToObject(json, "render", studio_render_to_json(s));
    cJSON_AddItemToObject(json, "timeline", timeline_to_json(&s->timeline));
    cJSON* texts = cJSON_AddArrayToObject(json, "texts");
    for (uint32 i = 0; i < s->texts.count; ++i)
        cJSON_AddItemToArray(texts, text_item_to_json(&s->texts.items[i]));
    return json;
}

b8
studio_from_json(studio* s, const cJSON* json, char* error, size_t error_size)
{
    const cJSON* c = cJSON_GetObjectItemCaseSensitive(json, "camera");
    const cJSON* l = cJSON_GetObjectItemCaseSensitive(json, "look_at");
    if ((c && !cJSON_IsString(c)) || (l && !cJSON_IsString(l)))
        return set_error(error, error_size, "\"camera\" and \"look_at\" must be entity names (\"\" = none)");
    const char* camera  = c ? c->valuestring : "";
    const char* look_at = l ? l->valuestring : "";
    if (strlen(camera) >= ENTITY_NAME_MAX || strlen(look_at) >= ENTITY_NAME_MAX)
        return set_error(error, error_size, "\"camera\" and \"look_at\" are at most %d characters", ENTITY_NAME_MAX - 1);

    // Everything is checked on copies first, so a bad file changes nothing.
    studio render = *s;
    const cJSON* render_json = cJSON_GetObjectItemCaseSensitive(json, "render");
    if (render_json && !studio_render_from_json(&render, render_json, error, error_size))
        return false;

    // The titles, into a copy of the item list.
    const cJSON* texts_json = cJSON_GetObjectItemCaseSensitive(json, "texts");
    text_item    texts[TEXT_MAX_ITEMS];
    uint32       text_count = 0;
    if (texts_json && (!cJSON_IsArray(texts_json) || cJSON_GetArraySize(texts_json) > TEXT_MAX_ITEMS))
        return set_error(error, error_size, "\"texts\" must be an array of at most %d titles", TEXT_MAX_ITEMS);
    const cJSON* text_json;
    cJSON_ArrayForEach(text_json, texts_json)
    {
        const char* name = NULL;
        if (arg_string(text_json, "name", &name, error, error_size) <= 0 || strlen(name) >= ENTITY_NAME_MAX)
            return set_error(error, error_size, "texts[%u] needs a \"name\"", text_count);
        text_item_defaults(&texts[text_count], name);
        if (!text_item_from_json(&s->texts, &texts[text_count], text_json, true, error, error_size))
            return false;
        ++text_count;
    }

    timeline loaded;
    timeline_init(&loaded);
    loaded.custom = s->timeline.custom;   // "Text" tracks are checked against the titles' fields
    const cJSON* timeline_json = cJSON_GetObjectItemCaseSensitive(json, "timeline");
    if (timeline_json && !timeline_from_json(&loaded, timeline_json, error, error_size))
    {
        timeline_destroy(&loaded);
        return false;
    }

    s->antialiasing = render.antialiasing;
    s->shadows      = render.shadows;
    glm_vec3_copy(render.clear_color, s->clear_color);
    snprintf(s->active_camera, sizeof(s->active_camera), "%s", camera);
    snprintf(s->look_at, sizeof(s->look_at), "%s", look_at);
    timeline_destroy(&s->timeline);
    s->timeline = loaded;
    memcpy(s->texts.items, texts, text_count * sizeof(*texts));
    s->texts.count = text_count;
    return true;
}

void
studio_scene_file(studio* s, cmd_scene_file_op op, const char* name)
{
    char relative[256];
    snprintf(relative, sizeof(relative), "scenes/%s.studio.json", name);
    char* path = project_path(relative);
    if (!path)
        return;

    if (op == CMD_SCENE_SAVED)
    {
        cJSON* json = studio_to_json(s);
        char*  text = cJSON_Print(json);
        if (!text || !file_write_string(path, text))
            LOG_ERROR("studio: couldn't write %s\n", path);
        cJSON_free(text);
        cJSON_Delete(json);
    }
    else
    {
        // A scene saved without a studio file: no timeline, no camera.
        char*  text  = file_exists(path) ? file_read_to_string(path) : NULL;
        cJSON* json  = text ? cJSON_Parse(text) : cJSON_CreateObject();
        char   error[256] = "not JSON";
        if (!json || !studio_from_json(s, json, error, sizeof(error)))
            LOG_ERROR("studio: %s isn't a valid studio file: %s\n", path, error);
        cJSON_Delete(json);
        free(text);
        studio_evaluate(s, 0.0f, NULL);
    }
    free(path);
}

// --- Rendering --------------------------------------------------------------------------

void
studio_render_settings(const studio* s, scene_render_settings* out)
{
    *out = scene_render_settings_default();
    scene_render_settings_apply_environment(out, s->env, s->ibl ? ibl_cache_maps(s->ibl) : NULL);
    out->antialiasing = s->antialiasing;
    out->shadows      = s->shadows;
    glm_vec3_copy((f32*)s->clear_color, out->clear_color);
}

entity_id
studio_camera_entity(studio* s, const char* name)
{
    entity_id e = world_find(s->w, name);
    if (!e)
        e = world_create(s->w, name);   // the name is free, so it's kept as given
    if (!world_camera(s->w, e))
        world_add_camera(s->w, e, STUDIO_DEFAULT_FOV, STUDIO_DEFAULT_NEAR, STUDIO_DEFAULT_FAR);
    return e;
}

b8
studio_camera_view(const studio* s, f32 aspect, camera* out)
{
    if (!s->active_camera[0])
        return false;
    return world_camera_view(s->w, world_find(s->w, s->active_camera), aspect, out);
}

b8
studio_look_rotation(const vec3 direction, vec3 out_rotation_deg)
{
    vec3 d;
    glm_vec3_copy((f32*)direction, d);
    if (glm_vec3_norm(d) < 1e-6f)
        return false;
    glm_vec3_normalize(d);

    // Ry(yaw) * Rx(pitch) takes -Z to (-cos(pitch) sin(yaw), sin(pitch), -cos(pitch) cos(yaw)).
    out_rotation_deg[0] = asinf(glm_clamp(d[1], -1.0f, 1.0f)) * RAD_TO_DEG;
    out_rotation_deg[1] = atan2f(-d[0], -d[2]) * RAD_TO_DEG;
    out_rotation_deg[2] = 0.0f;
    return true;
}
