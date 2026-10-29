// lighting.preset: a studio lighting setup placed around a subject. Every
// light is a spot aimed at the subject's centre, at `azimuth` / `elevation`
// degrees around it (as camera.move measures them: 0 = from the front, +Z)
// and a distance that grows with the subject's size. Intensities scale with
// that distance squared, so a preset lights a small bottle and a large box
// the same way.
//
// A preset's lights are entities called light_<role> ("light_key",
// "light_rim_left", ...): applying a preset removes the previous preset's
// lights, and each one can still be changed or keyframed by name.
//
// `glow` adds light_glow: a soft pool of light on the backdrop's wall right
// behind the subject. Glass shows what's behind it, so on a dark set it reads
// dark; with a glow behind it, it lights up in the colour of what it holds --
// the backlit bottle of every perfume advert.

#include "LightingCommands.h"

#include "Common/Json.h"
#include "Studio.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define DEG_TO_RAD (3.14159265358979f / 180.0f)

#define LIGHT_PREFIX "light_"

// A light of intensity 1 x REFERENCE_INTENSITY at REFERENCE_DISTANCE meters
// lights a subject about as a key light should.
#define REFERENCE_INTENSITY 6.0f
#define REFERENCE_DISTANCE  1.5f

// The glow: a spot up and out from the wall (shares of the subject's distance
// to it), aimed at the wall behind the subject, its pool's radius a share of
// that distance too -- wide, so the glass still has light behind it when the
// camera is 30-40 degrees round, and fully soft-edged.
#define GLOW_LIFT    0.4f
#define GLOW_REACH   0.5f
#define GLOW_POOL    0.8f
#define GLOW_KELVIN  3400.0f   // warm, as a backlight usually is

typedef struct preset_light
{
    const char* role;
    f32         azimuth, elevation;
    f32         intensity;   // times REFERENCE_INTENSITY
    f32         kelvin;      // colour temperature; 0 = use `color`
    f32         color[3];
    b8          shadows;
} preset_light;

typedef struct lighting_preset
{
    const char*  name;
    const char*  doc;
    preset_light lights[4];
    uint32       count;
} lighting_preset;

static const lighting_preset PRESETS[] = {
    { "three_point", "classic: a key from the front left, a soft fill, a rim from behind", {
        { "key", -40, 30, 1.0f, 5200, { 0 }, true },
        { "fill", 50, 10, 0.35f, 6000, { 0 }, false },
        { "rim", 160, 35, 1.4f, 5600, { 0 }, true } }, 3 },
    { "rim_dark", "luxury, dark and moody: a faint key, warm and cool rims tracing the edges", {
        { "key", -35, 25, 0.4f, 4800, { 0 }, true },
        { "rim_left", -140, 6, 4.0f, 3000, { 0 }, true },
        { "rim_right", 140, 6, 3.0f, 9000, { 0 }, true } }, 3 },
    { "high_key", "clean and bright: soft light from everywhere, few shadows (pair with a light backdrop)", {
        { "key", -30, 35, 1.0f, 6000, { 0 }, true },
        { "fill", 35, 20, 0.8f, 6000, { 0 }, false },
        { "top", 0, 80, 0.8f, 6000, { 0 }, false },
        { "back", 180, 20, 0.6f, 6000, { 0 }, false } }, 4 },
    { "top_soft", "light falling from above, like a skylight; dark below", {
        { "top", -10, 75, 1.4f, 5600, { 0 }, true },
        { "fill", 0, 5, 0.2f, 5600, { 0 }, false } }, 2 },
    { "split", "half lit, half dark: dramatic, one hard light from the side", {
        { "key", -90, 10, 1.6f, 5000, { 0 }, true } }, 1 },
    { "neon_dual", "bold and energetic: magenta and cyan rims from either side", {
        { "key", 0, 20, 0.2f, 6500, { 0 }, false },
        { "rim_left", -110, 5, 3.5f, 0, { 1.0f, 0.15f, 0.75f }, true },
        { "rim_right", 110, 5, 3.5f, 0, { 0.1f, 0.85f, 1.0f }, true } }, 3 },
};
#define PRESET_COUNT (sizeof(PRESETS) / sizeof(PRESETS[0]))

// Blackbody colour, normalized so its brightest channel is 1, as linear RGB
// (Tanner Helland's fit, good to a few percent from 1000 to 40000 K).
static void
kelvin_to_rgb(f32 kelvin, f32 out[3])
{
    f32 t = glm_clamp(kelvin, 1000.0f, 40000.0f) / 100.0f;
    f32 r = t <= 66.0f ? 255.0f : 329.698727446f * powf(t - 60.0f, -0.1332047592f);
    f32 g = t <= 66.0f ? 99.4708025861f * logf(t) - 161.1195681661f : 288.1221695283f * powf(t - 60.0f, -0.0755148492f);
    f32 b = t >= 66.0f ? 255.0f : t <= 19.0f ? 0.0f : 138.5177312231f * logf(t - 10.0f) - 305.0447927307f;
    f32 srgb[3] = { glm_clamp(r, 0.0f, 255.0f) / 255.0f, glm_clamp(g, 0.0f, 255.0f) / 255.0f, glm_clamp(b, 0.0f, 255.0f) / 255.0f };
    f32 top = 0.0f;
    for (int i = 0; i < 3; ++i)
    {
        f32 c  = srgb[i];
        out[i] = c <= 0.04045f ? c / 12.92f : powf((c + 0.055f) / 1.055f, 2.4f);
        top    = fmaxf(top, out[i]);
    }
    for (int i = 0; i < 3; ++i)
        out[i] /= top;
}

// Destroys every light_* entity with a Light. Returns how many.
static uint32
remove_preset_lights(world* w)
{
    entity_id doomed[64];
    uint32    count = 0;
    for (entity_id e = world_next(w, ENTITY_NULL, COMPONENT_BIT(COMPONENT_LIGHT)); e && count < 64;
         e = world_next(w, e, COMPONENT_BIT(COMPONENT_LIGHT)))
    {
        if (strncmp(world_name(w, e), LIGHT_PREFIX, strlen(LIGHT_PREFIX)) == 0)
            doomed[count++] = e;
    }
    for (uint32 i = 0; i < count; ++i)
        world_destroy(w, doomed[i]);
    return count;
}

static b8
cmd_lighting_preset(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    const char* name    = NULL;
    const char* subject = NULL;
    f32 intensity = 1.0f, turn = 0.0f, warmth = 0.0f, glow = 0.0f, glow_color[4] = { 1.0f, 1.0f, 1.0f, 1.0f };
    int has_glow_color = 0;
    if (arg_string(args, "name", &name, error, error_size) < 0 || arg_string(args, "subject", &subject, error, error_size) < 0
        || arg_number(args, "intensity", 0.0f, 20.0f, &intensity, error, error_size) < 0
        || arg_number(args, "turn", -360.0f, 360.0f, &turn, error, error_size) < 0
        || arg_number(args, "warmth", -1.0f, 1.0f, &warmth, error, error_size) < 0
        || arg_number(args, "glow", 0.0f, 20.0f, &glow, error, error_size) < 0
        || (has_glow_color = arg_color(args, "glow_color", glow_color, error, error_size)) < 0)
        return false;

    const lighting_preset* preset = NULL;
    for (uint32 i = 0; name && i < PRESET_COUNT; ++i)
        preset = strcmp(name, PRESETS[i].name) == 0 ? &PRESETS[i] : preset;
    if (!preset)
    {
        char list[256] = "";
        for (uint32 i = 0; i < PRESET_COUNT; ++i)
            snprintf(list + strlen(list), sizeof(list) - strlen(list), "%s%s", i ? ", " : "", PRESETS[i].name);
        return set_error(error, error_size, "\"name\" must be one of: %s", list);
    }

    entity_id e = subject ? world_find(s->w, subject) : ENTITY_NULL;
    vec3      lo, hi;
    if (!e || !world_bounds(s->w, e, lo, hi))
        return set_error(error, error_size, "\"subject\" must name an entity with a MeshRenderer and a model");
    vec3 center;
    glm_vec3_center(lo, hi, center);
    f32 radius   = fmaxf(0.5f * glm_vec3_distance(lo, hi), 0.01f);
    f32 distance = fmaxf(5.0f * radius, 0.6f);
    f32 falloff  = (distance / REFERENCE_DISTANCE) * (distance / REFERENCE_DISTANCE);
    f32 outer    = atanf(1.6f * radius / distance) / DEG_TO_RAD + 4.0f;

    remove_preset_lights(s->w);

    cJSON* lights = cJSON_CreateArray();
    for (uint32 i = 0; i < preset->count; ++i)
    {
        const preset_light* p = &preset->lights[i];
        f32 az = (p->azimuth + turn) * DEG_TO_RAD, el = p->elevation * DEG_TO_RAD;
        vec3 position = { center[0] + distance * sinf(az) * cosf(el), center[1] + distance * sinf(el),
                          center[2] + distance * cosf(az) * cosf(el) };
        vec3 direction;
        glm_vec3_sub(center, position, direction);
        glm_vec3_normalize(direction);

        // warmth shifts every light's temperature: +1 = 1500 K warmer, -1 = cooler.
        f32 color[3];
        if (p->kelvin > 0.0f)
            kelvin_to_rgb(p->kelvin - 1500.0f * warmth, color);
        else
            memcpy(color, p->color, sizeof(color));

        light l;
        light_init_spot(&l, direction, color, p->intensity * REFERENCE_INTENSITY * falloff * intensity,
                        3.0f * distance, 0.6f * outer, outer);
        l.cast_shadows = p->shadows;

        char light_name[ENTITY_NAME_MAX];
        snprintf(light_name, sizeof(light_name), LIGHT_PREFIX "%s", p->role);
        entity_id light_entity = world_create(s->w, light_name);
        glm_vec3_copy(position, world_transform(s->w, light_entity)->position);
        world_add_light(s->w, light_entity, l);

        cJSON* item = cJSON_CreateObject();
        cJSON_AddStringToObject(item, "entity", world_name(s->w, light_entity));
        json_add_floats(item, "position", position, 3);
        cJSON_AddNumberToObject(item, "intensity", json_round6(l.intensity));
        json_add_floats(item, "color", color, 3);
        cJSON_AddItemToArray(lights, item);
    }
    if (glow > 0.0f)
    {
        // The wall: the back of the backdrop entity, or where a default cyclorama's would be.
        entity_id backdrop = world_find(s->w, "backdrop");
        vec3      back_lo, back_hi;
        f32       wall = center[2] - 3.0f;
        if (backdrop && world_bounds(s->w, backdrop, back_lo, back_hi))
            wall = back_lo[2];

        f32  gap    = fmaxf(center[2] - wall, 0.5f);
        vec3 aim    = { center[0], center[1] - 0.1f * gap, wall + 0.01f };   // the camera looks a little down: the glass sees the wall below its own height
        vec3 source = { aim[0], aim[1] + GLOW_LIFT * gap, aim[2] + GLOW_REACH * gap };
        vec3 direction;
        glm_vec3_sub(aim, source, direction);
        f32  reach = glm_vec3_norm(direction);
        glm_vec3_normalize(direction);
        f32  cone  = atanf(GLOW_POOL * gap / reach) / DEG_TO_RAD;

        f32 color[3];
        if (has_glow_color)
            memcpy(color, glow_color, sizeof(color));
        else
            kelvin_to_rgb(GLOW_KELVIN - 1500.0f * warmth, color);
        f32 glow_falloff = (reach / REFERENCE_DISTANCE) * (reach / REFERENCE_DISTANCE);

        light l;
        light_init_spot(&l, direction, color, glow * REFERENCE_INTENSITY * glow_falloff, 3.0f * reach, 0.0f, cone);
        l.cast_shadows = false;
        entity_id light_entity = world_create(s->w, LIGHT_PREFIX "glow");
        glm_vec3_copy(source, world_transform(s->w, light_entity)->position);
        world_add_light(s->w, light_entity, l);

        cJSON* item = cJSON_CreateObject();
        cJSON_AddStringToObject(item, "entity", world_name(s->w, light_entity));
        json_add_floats(item, "position", source, 3);
        cJSON_AddNumberToObject(item, "intensity", json_round6(l.intensity));
        json_add_floats(item, "color", color, 3);
        cJSON_AddItemToArray(lights, item);
    }
    studio_evaluate(s, s->timeline.time, NULL);

    *out_result = cJSON_CreateObject();
    cJSON_AddStringToObject(*out_result, "preset", preset->name);
    cJSON_AddStringToObject(*out_result, "look", preset->doc);
    cJSON_AddItemToObject(*out_result, "lights", lights);
    return true;
}

static const cmd_arg PRESET_ARGS[] = {
    { "name", "string", true, "three_point, rim_dark (luxury, moody), high_key (clean, bright), top_soft, split (dramatic) or neon_dual (bold)" },
    { "subject", "string", true, "the entity to light (the product)" },
    { "intensity", "number", false, "times the preset's brightness, 0 to 20 (default 1)" },
    { "turn", "number", false, "degrees to turn the whole setup around the subject (default 0)" },
    { "warmth", "number", false, "-1 (cooler) to 1 (warmer); 0 = the preset's own colours" },
    { "glow", "number", false, "a soft pool of light on the backdrop's wall behind the subject (light_glow): glass "
                               "lights up in it; 0 none (default), 1 subtle, 3 strong" },
    { "glow_color", "string", false, "the glow's colour, \"#RRGGBB\" (default warm, following warmth)" },
};

static const cmd_host_command LIGHTING_COMMANDS[] = {
    { "lighting.preset", "Replaces the preset lights (light_*) with a studio lighting setup around the subject. "
                         "Each light is then an ordinary entity: change or keyframe it by name.",
      PRESET_ARGS, sizeof(PRESET_ARGS) / sizeof(PRESET_ARGS[0]), true, cmd_lighting_preset },
};

const cmd_host_command*
lighting_commands(uint32* out_count)
{
    *out_count = sizeof(LIGHTING_COMMANDS) / sizeof(LIGHTING_COMMANDS[0]);
    return LIGHTING_COMMANDS;
}
