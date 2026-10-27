// product.create and backdrop.create: models built from a few numbers,
// written as glTF under the project's products/ folder (Geometry.h) and put
// on an entity.
//
//   product.create   a product spun from a profile -- a template (perfume,
//                    bottle, jar, can, dropper) or the caller's own parts --
//                    with an optional label image wrapped around its body
//   backdrop.create  a cyclorama (a floor curving up into a wall) or a
//                    round pedestal
//
// A model's file name carries a hash of everything it's made from, so the
// same request reuses its file and a changed one gets a new file (the
// engine caches models by path).

#include "ProductCommands.h"

#include "Common/Json.h"
#include "Core/FileIO.h"
#include "Core/Paths.h"
#include "Geometry.h"
#include "Studio/Studio.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_PARTS          8
#define MAX_PROFILE_POINTS 64
#define LABEL_LIFT         0.0006f   // meters the label stands off the glass, so it doesn't flicker into it

// --- Templates ------------------------------------------------------------------------
// Profiles in units of the product's radius (r) and height (y), bottom to top.

typedef struct part_template
{
    const char*       name;
    geo_profile_point points[16];
    uint32            count;
    geo_material      material;
} part_template;

typedef struct product_template
{
    const char*   name;
    f32           height, width;              // meters, by default
    f32           label_from, label_to;       // the label band, as fractions of the height
    part_template parts[4];
    uint32        part_count;
} product_template;

#define GLASS(r, g, b, a) { .base_color = { r, g, b, a }, .metallic = 0.0f, .roughness = 0.05f }
#define METAL(r, g, b, rough) { .base_color = { r, g, b, 1.0f }, .metallic = 1.0f, .roughness = rough }
#define MATTE(r, g, b, rough) { .base_color = { r, g, b, 1.0f }, .metallic = 0.0f, .roughness = rough }

static const product_template TEMPLATES[] = {
    { "perfume", 0.12f, 0.08f, 0.22f, 0.56f, {
        { "body", { { 0, 0 }, { 0.9f, 0 }, { 1, 0.03f }, { 1, 0.62f }, { 0.9f, 0.7f }, { 0.45f, 0.74f }, { 0.22f, 0.76f } }, 7,
          GLASS(0.12f, 0.03f, 0.08f, 1.0f) },
        { "cap", { { 0, 0.76f }, { 0.36f, 0.76f }, { 0.38f, 0.78f }, { 0.38f, 0.98f }, { 0.34f, 1 }, { 0, 1 } }, 6,
          METAL(1.0f, 0.77f, 0.38f, 0.22f) } }, 2 },
    { "bottle", 0.30f, 0.075f, 0.18f, 0.5f, {
        { "body", { { 0, 0 }, { 0.95f, 0 }, { 1, 0.02f }, { 1, 0.55f }, { 0.9f, 0.65f }, { 0.4f, 0.78f }, { 0.32f, 0.82f }, { 0.32f, 0.92f } }, 8,
          GLASS(0.05f, 0.12f, 0.06f, 1.0f) },
        { "cap", { { 0, 0.92f }, { 0.36f, 0.92f }, { 0.36f, 1 }, { 0, 1 } }, 4, METAL(0.8f, 0.8f, 0.82f, 0.3f) } }, 2 },
    { "jar", 0.07f, 0.09f, 0.15f, 0.62f, {
        { "body", { { 0, 0 }, { 0.95f, 0 }, { 1, 0.04f }, { 1, 0.72f }, { 0.92f, 0.74f }, { 0.92f, 0.76f } }, 6,
          MATTE(0.92f, 0.9f, 0.86f, 0.35f) },
        { "lid", { { 0, 0.76f }, { 1.02f, 0.76f }, { 1.04f, 0.78f }, { 1.04f, 0.98f }, { 1, 1 }, { 0, 1 } }, 6,
          METAL(0.85f, 0.85f, 0.85f, 0.25f) } }, 2 },
    { "can", 0.122f, 0.066f, 0.12f, 0.86f, {
        { "body", { { 0, 0 }, { 0.78f, 0 }, { 0.85f, 0.02f }, { 1, 0.08f }, { 1, 0.88f }, { 0.86f, 0.97f }, { 0.84f, 1 }, { 0, 1 } }, 8,
          METAL(0.9f, 0.91f, 0.93f, 0.25f) } }, 1 },
    { "dropper", 0.11f, 0.04f, 0.12f, 0.52f, {
        { "body", { { 0, 0 }, { 0.95f, 0 }, { 1, 0.03f }, { 1, 0.6f }, { 0.85f, 0.66f }, { 0.4f, 0.7f }, { 0.4f, 0.74f } }, 7,
          GLASS(0.35f, 0.18f, 0.06f, 1.0f) },
        { "collar", { { 0, 0.74f }, { 0.48f, 0.74f }, { 0.48f, 0.8f }, { 0, 0.8f } }, 4, METAL(1.0f, 0.77f, 0.38f, 0.25f) },
        { "bulb", { { 0, 0.8f }, { 0.42f, 0.8f }, { 0.44f, 0.86f }, { 0.4f, 0.94f }, { 0.25f, 0.99f }, { 0, 1 } }, 6,
          MATTE(0.02f, 0.02f, 0.02f, 0.6f) } }, 3 },
};
#define TEMPLATE_COUNT (sizeof(TEMPLATES) / sizeof(TEMPLATES[0]))

// --- Reading arguments ------------------------------------------------------------------

// "#RRGGBB" (sRGB, as palettes give colours) into linear RGB.
static b8
parse_hex(const char* text, f32 out[3])
{
    unsigned value;
    if (!text || text[0] != '#' || strlen(text) != 7 || sscanf(text + 1, "%6x", &value) != 1)
        return false;
    for (int i = 0; i < 3; ++i)
    {
        f32 c = (f32)((value >> (16 - 8 * i)) & 0xFF) / 255.0f;
        out[i] = c <= 0.04045f ? c / 12.92f : powf((c + 0.055f) / 1.055f, 2.4f);
    }
    return true;
}

// A colour: "#RRGGBB" (sRGB) or [r, g, b] (linear). 1 read, 0 absent, -1 invalid.
static int
arg_color(const cJSON* args, const char* name, f32 out[3], char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (cJSON_IsString(item) ? parse_hex(item->valuestring, out) : json_read_floats(item, out, 3))
        return 1;
    return set_error(error, error_size, "\"%s\" must be \"#RRGGBB\" (sRGB) or [r, g, b] (linear 0..1)", name), -1;
}

// A material's overrides from JSON: color, opacity, metallic, roughness, emissive.
static b8
read_material(const cJSON* json, geo_material* m, char* error, size_t error_size)
{
    f32 opacity = m->base_color[3];
    if (arg_color(json, "color", m->base_color, error, error_size) < 0
        || arg_number(json, "opacity", 0.02f, 1.0f, &opacity, error, error_size) < 0
        || arg_number(json, "metallic", 0.0f, 1.0f, &m->metallic, error, error_size) < 0
        || arg_number(json, "roughness", 0.0f, 1.0f, &m->roughness, error, error_size) < 0
        || arg_color(json, "emissive", m->emissive, error, error_size) < 0)
        return false;
    m->base_color[3] = opacity;
    return true;
}

static b8
read_profile(const cJSON* json, geo_profile_point* out, uint32* count, char* error, size_t error_size)
{
    int n = cJSON_IsArray(json) ? cJSON_GetArraySize(json) : 0;
    if (n < 2 || n > MAX_PROFILE_POINTS)
        return set_error(error, error_size, "a \"profile\" is 2 to %d points [radius, height] in meters, bottom to top", MAX_PROFILE_POINTS);
    for (int i = 0; i < n; ++i)
    {
        f32 p[2];
        if (!json_read_floats(cJSON_GetArrayItem(json, i), p, 2) || p[0] < 0.0f)
            return set_error(error, error_size, "profile point %d must be [radius, height] with radius >= 0", i);
        out[i] = (geo_profile_point){ p[0], p[1] };
    }
    *count = (uint32)n;
    return true;
}

// --- Building ------------------------------------------------------------------------------

typedef struct product_part
{
    char              name[32];
    geo_profile_point profile[MAX_PROFILE_POINTS];
    uint32            count;
    geo_material      material;
} product_part;

// The body's radius at height y (the profile's outermost crossing), 0 if none.
static f32
radius_at(const product_part* part, f32 y)
{
    f32 r = 0.0f;
    for (uint32 i = 0; i + 1 < part->count; ++i)
    {
        geo_profile_point a = part->profile[i], b = part->profile[i + 1];
        if ((y - a.y) * (y - b.y) <= 0.0f && fabsf(b.y - a.y) > 1e-7f)
            r = fmaxf(r, glm_lerp(a.r, b.r, (y - a.y) / (b.y - a.y)));
    }
    return r;
}

static uint64
fnv1a(uint64 hash, const void* data, size_t size)
{
    const uint8* bytes = data;
    for (size_t i = 0; i < size; ++i)
        hash = (hash ^ bytes[i]) * 1099511628211ull;
    return hash;
}

// The 8 hex digits a generated file's name carries.
static unsigned
short_hash(uint64 hash)
{
    return (unsigned)(hash ^ (hash >> 32));
}

// `hash` continued over a file's bytes (binary: images have NULs early on).
static uint64
fnv1a_file(uint64 hash, const char* path)
{
    FILE* file = fopen(path, "rb");
    if (!file)
        return hash;
    uint8  chunk[16384];
    size_t read;
    while ((read = fread(chunk, 1, sizeof(chunk), file)) > 0)
        hash = fnv1a(hash, chunk, read);
    fclose(file);
    return hash;
}

// The products/ folder, made if missing. Caller frees.
static char*
products_dir(char* error, size_t error_size)
{
    char* dir = project_path("products");
    if (!dir || (!file_is_directory(dir) && !file_make_directories(dir)))
    {
        set_error(error, error_size, "couldn't make the project's products folder");
        free(dir);
        return NULL;
    }
    return dir;
}

// Writes `parts` as products/<name>_<hash>.gltf, loads it, and puts it on
// the entity `name` (made if missing) at `position` (if given).
static b8
build_and_place(studio* s, const char* name, geo_part* parts, uint32 count, uint64 hash, const f32* position,
                cJSON** out_result, char* error, size_t error_size)
{
    char* dir = products_dir(error, error_size);
    if (!dir)
        return false;
    char key[160], path[1200];
    snprintf(key, sizeof(key), "products/%s_%08x.gltf", name, short_hash(hash));
    snprintf(path, sizeof(path), "%s/%s", dir, key + strlen("products/"));
    free(dir);

    if (!file_exists(path) && !geo_write_gltf(path, parts, count, error, error_size))
        return false;
    asset_id model = assets_load_model(s->w->assets, key);
    if (model == ASSET_NONE)
        return set_error(error, error_size, "the engine couldn't load %s", path);

    entity_id e = world_find(s->w, name);
    if (!e)
        e = world_create(s->w, name);
    if (world_mesh_renderer(s->w, e))
        world_set_model(s->w, e, model);
    else
        world_add_mesh_renderer(s->w, e, model);
    if (position)
        glm_vec3_copy((f32*)position, world_transform(s->w, e)->position);
    studio_evaluate(s, s->timeline.time, NULL);

    vec3 lo, hi;
    *out_result = cJSON_CreateObject();
    cJSON_AddStringToObject(*out_result, "entity", name);
    cJSON_AddStringToObject(*out_result, "model", key);
    if (world_bounds(s->w, e, lo, hi))
    {
        json_add_floats(*out_result, "bounds_min", lo, 3);
        json_add_floats(*out_result, "bounds_max", hi, 3);
    }
    return true;
}

// The entity name every command here needs.
static b8
read_name(const cJSON* args, const char* fallback, const char** out, char* error, size_t error_size)
{
    *out = fallback;
    if (arg_string(args, "name", out, error, error_size) < 0)
        return false;
    if (!*out)
        return set_error(error, error_size, "\"name\" must be given: the entity to put it on");
    for (const char* c = *out; *c; ++c)
    {
        if (!((*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') || (*c >= '0' && *c <= '9') || *c == '_' || *c == '-'))
            return set_error(error, error_size, "\"name\" may only use letters, digits, '_' and '-' (it names a file)");
    }
    if (strlen(*out) > 40)
        return set_error(error, error_size, "\"name\" is at most 40 characters");
    return true;
}

// --- product.create -------------------------------------------------------------------------

static b8
read_parts(const cJSON* args, const product_template* t, f32 height, f32 width, product_part* parts, uint32* count,
           char* error, size_t error_size)
{
    const cJSON* parts_json = cJSON_GetObjectItemCaseSensitive(args, "parts");
    *count = 0;
    if (t)
    {
        // The template's parts, scaled, with any colour or finish the caller gives by part name.
        if (parts_json && !cJSON_IsObject(parts_json))
            return set_error(error, error_size, "with a template, \"parts\" is an object of part names, e.g. {\"cap\": {\"color\": \"#c9a45c\"}}");
        for (uint32 p = 0; p < t->part_count; ++p)
        {
            product_part* part = &parts[(*count)++];
            snprintf(part->name, sizeof(part->name), "%s", t->parts[p].name);
            part->count    = t->parts[p].count;
            part->material = t->parts[p].material;
            for (uint32 i = 0; i < part->count; ++i)
                part->profile[i] = (geo_profile_point){ t->parts[p].points[i].r * 0.5f * width, t->parts[p].points[i].y * height };
            const cJSON* overrides = parts_json ? cJSON_GetObjectItemCaseSensitive(parts_json, part->name) : NULL;
            char part_error[200];
            if (overrides && !read_material(overrides, &part->material, part_error, sizeof(part_error)))
                return set_error(error, error_size, "parts.%s: %s", part->name, part_error);
        }
        const cJSON* item;
        cJSON_ArrayForEach(item, parts_json)
        {
            b8 known = false;
            for (uint32 p = 0; p < t->part_count; ++p)
                known = known || strcmp(item->string, t->parts[p].name) == 0;
            if (!known)
                return set_error(error, error_size, "the %s template has no part \"%s\"", t->name, item->string);
        }
        return true;
    }

    // The caller's own parts: [{name, profile, color, ...}].
    int n = cJSON_IsArray(parts_json) ? cJSON_GetArraySize(parts_json) : 0;
    if (n < 1 || n > MAX_PARTS)
        return set_error(error, error_size, "without a template, \"parts\" is an array of 1 to %d "
                         "{\"name\", \"profile\": [[radius, height], ...], \"color\", ...}", MAX_PARTS);
    for (int p = 0; p < n; ++p)
    {
        const cJSON*  json = cJSON_GetArrayItem(parts_json, p);
        product_part* part = &parts[(*count)++];
        const char*   name = "part";
        char          part_error[200];
        part->material = (geo_material)MATTE(0.8f, 0.8f, 0.8f, 0.4f);
        if (arg_string(json, "name", &name, part_error, sizeof(part_error)) < 0
            || !read_profile(cJSON_GetObjectItemCaseSensitive(json, "profile"), part->profile, &part->count, part_error, sizeof(part_error))
            || !read_material(json, &part->material, part_error, sizeof(part_error)))
            return set_error(error, error_size, "parts[%d]: %s", p, part_error);
        snprintf(part->name, sizeof(part->name), "%s", name);
    }
    return true;
}

static b8
cmd_product_create(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    const char* name;
    const char* template_name = NULL;
    if (!read_name(args, NULL, &name, error, error_size) || arg_string(args, "template", &template_name, error, error_size) < 0)
        return false;
    const product_template* t = NULL;
    for (uint32 i = 0; template_name && i < TEMPLATE_COUNT; ++i)
        t = strcmp(template_name, TEMPLATES[i].name) == 0 ? &TEMPLATES[i] : t;
    if (template_name && !t)
        return set_error(error, error_size, "\"template\" must be perfume, bottle, jar, can or dropper (or leave it out and give \"parts\")");

    f32 height = t ? t->height : 1.0f, width = t ? t->width : 1.0f, segments = 96;
    vec3 position;
    int  has_position = arg_vec3(args, "position", position, error, error_size);
    if (arg_number(args, "height", 0.005f, 5.0f, &height, error, error_size) < 0
        || arg_number(args, "width", 0.005f, 5.0f, &width, error, error_size) < 0
        || arg_number(args, "segments", 12, 256, &segments, error, error_size) < 0 || has_position < 0)
        return false;

    product_part parts[MAX_PARTS];
    uint32       part_count;
    if (!read_parts(args, t, height, width, parts, &part_count, error, error_size))
        return false;

    // The label: an image wrapped around a band of one part, standing just off it.
    const cJSON* label_json = cJSON_GetObjectItemCaseSensitive(args, "label");
    const char*  image      = NULL;
    const char*  label_part = "body";
    f32          label_from = t ? t->label_from * height : 0.25f * height;
    f32          label_to   = t ? t->label_to * height : 0.6f * height;
    f32          arc        = 150.0f;
    if (label_json)
    {
        if (!cJSON_IsObject(label_json) || arg_string(label_json, "image", &image, error, error_size) <= 0)
            return set_error(error, error_size, "\"label\" is {\"image\": a PNG or JPG path, \"part\", \"from\", \"to\" (meters up), \"arc\" (degrees)}");
        if (arg_string(label_json, "part", &label_part, error, error_size) < 0
            || arg_number(label_json, "from", -10.0f, 10.0f, &label_from, error, error_size) < 0
            || arg_number(label_json, "to", -10.0f, 10.0f, &label_to, error, error_size) < 0
            || arg_number(label_json, "arc", 5.0f, 360.0f, &arc, error, error_size) < 0)
            return false;
        if (label_to <= label_from)
            return set_error(error, error_size, "the label's \"to\" (%g) must be above its \"from\" (%g)", label_to, label_from);
        if (!file_exists(image))
            return set_error(error, error_size, "no label image at %s", image);
    }

    // What the model is made of decides its file: the request, and the label's bytes.
    char*  spec = cJSON_PrintUnformatted(args);
    uint64 hash = fnv1a(14695981039346656037ull, spec, strlen(spec));
    cJSON_free(spec);
    if (image)
        hash = fnv1a_file(hash, image);

    geo_part geo[MAX_PARTS + 1];
    uint32   geo_count = 0;
    for (uint32 p = 0; p < part_count; ++p)
    {
        geo_part_init(&geo[geo_count], parts[p].name, &parts[p].material);
        geo_lathe(&geo[geo_count++], parts[p].profile, parts[p].count, (uint32)segments, -180.0f, 180.0f, 35.0f, 0.0f, 0.0f);
    }

    char label_uri[128] = "";
    b8   ok             = true;
    if (image)
    {
        const product_part* body = NULL;
        for (uint32 p = 0; p < part_count; ++p)
            body = strcmp(parts[p].name, label_part) == 0 ? &parts[p] : body;
        if (!body)
            ok = set_error(error, error_size, "the label's \"part\" \"%s\" isn't one of the product's parts", label_part);

        // The band follows the part's surface between the two heights.
        geo_profile_point band[MAX_PROFILE_POINTS + 2];
        uint32            band_count = 0;
        if (ok)
        {
            band[band_count++] = (geo_profile_point){ radius_at(body, label_from) + LABEL_LIFT, label_from };
            for (uint32 i = 0; i < body->count; ++i)
            {
                if (body->profile[i].y > label_from && body->profile[i].y < label_to)
                    band[band_count++] = (geo_profile_point){ body->profile[i].r + LABEL_LIFT, body->profile[i].y };
            }
            band[band_count++] = (geo_profile_point){ radius_at(body, label_to) + LABEL_LIFT, label_to };
            if (band[0].r <= LABEL_LIFT || band[band_count - 1].r <= LABEL_LIFT)
                ok = set_error(error, error_size, "the label's band (%g to %g m) isn't on the %s's side", label_from, label_to, label_part);
        }

        // The image goes next to the model, which refers to it by name.
        char* dir = ok ? products_dir(error, error_size) : NULL;
        if (dir)
        {
            const char* extension = strrchr(image, '.');
            snprintf(label_uri, sizeof(label_uri), "%s_%08x_label%s", name, short_hash(hash), extension ? extension : ".png");
            char destination[1200];
            snprintf(destination, sizeof(destination), "%s/%s", dir, label_uri);
            ok = file_copy(image, destination) || set_error(error, error_size, "couldn't copy the label to %s", destination);
            free(dir);
        }
        else
            ok = false;

        if (ok)
        {
            geo_material paper = MATTE(1.0f, 1.0f, 1.0f, 0.55f);
            paper.texture      = label_uri;
            paper.alpha_mask   = true;
            geo_part_init(&geo[geo_count], "label", &paper);
            geo_lathe(&geo[geo_count++], band, band_count, (uint32)segments, -0.5f * arc, 0.5f * arc, 35.0f, label_to, label_from);
        }
    }

    if (ok)
        ok = build_and_place(s, name, geo, geo_count, hash, has_position ? position : NULL, out_result, error, error_size);
    for (uint32 p = 0; p < geo_count; ++p)
        geo_part_free(&geo[p]);
    if (!ok)
        return false;

    cJSON* names = cJSON_AddArrayToObject(*out_result, "parts");
    for (uint32 p = 0; p < part_count; ++p)
        cJSON_AddItemToArray(names, cJSON_CreateString(parts[p].name));
    cJSON_AddBoolToObject(*out_result, "label", image != NULL);
    return true;
}

// --- backdrop.create ----------------------------------------------------------------------

static b8
cmd_backdrop_create(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    const char* kind = "cyclorama";
    const char* name;
    const char* texture = NULL;
    if (arg_string(args, "kind", &kind, error, error_size) < 0 || arg_string(args, "texture", &texture, error, error_size) < 0)
        return false;
    b8 cyclorama = strcmp(kind, "cyclorama") == 0;
    if (!cyclorama && strcmp(kind, "pedestal") != 0)
        return set_error(error, error_size, "\"kind\" must be \"cyclorama\" or \"pedestal\"");
    if (!read_name(args, cyclorama ? "backdrop" : "pedestal", &name, error, error_size))
        return false;

    // Sizes in meters; a pedestal's width is its diameter.
    f32 width = cyclorama ? 8.0f : 0.5f, depth = 6.0f, height = cyclorama ? 4.0f : 0.3f;
    f32 radius = 1.2f, tile = 0.0f;
    vec3 position;
    int  has_position = arg_vec3(args, "position", position, error, error_size);
    geo_material m = MATTE(0.02f, 0.02f, 0.022f, cyclorama ? 0.65f : 0.6f);
    if (arg_number(args, "width", 0.01f, 100.0f, &width, error, error_size) < 0
        || arg_number(args, "depth", 0.1f, 100.0f, &depth, error, error_size) < 0
        || arg_number(args, "height", 0.01f, 100.0f, &height, error, error_size) < 0
        || arg_number(args, "radius", 0.0f, 50.0f, &radius, error, error_size) < 0
        || arg_number(args, "texture_tile", 0.0f, 100.0f, &tile, error, error_size) < 0
        || has_position < 0 || !read_material(args, &m, error, error_size))
        return false;
    if (texture && !file_exists(texture))
        return set_error(error, error_size, "no texture image at %s", texture);
    radius = fminf(radius, fminf(depth, height));

    char*  spec = cJSON_PrintUnformatted(args);
    uint64 hash = fnv1a(14695981039346656037ull, spec, strlen(spec));
    cJSON_free(spec);
    if (texture)
        hash = fnv1a_file(hash, texture);

    char texture_uri[128] = "";
    if (texture)
    {
        char* dir = products_dir(error, error_size);
        if (!dir)
            return false;
        const char* extension = strrchr(texture, '.');
        snprintf(texture_uri, sizeof(texture_uri), "%s_%08x_surface%s", name, short_hash(hash), extension ? extension : ".png");
        char destination[1200];
        snprintf(destination, sizeof(destination), "%s/%s", dir, texture_uri);
        free(dir);
        if (!file_copy(texture, destination))
            return set_error(error, error_size, "couldn't copy the texture to %s", destination);
        m.texture        = texture_uri;
        m.texture_repeat = true;
        glm_vec3_one(m.base_color);   // the image is the colour
    }

    geo_part part;
    geo_part_init(&part, kind, &m);
    if (cyclorama)
    {
        // Front to back along the floor, a quarter circle up, then the wall.
        geo_profile_point profile[24];
        uint32 n = 0;
        f32 front = 0.5f * depth, back = -0.5f * depth;
        profile[n++] = (geo_profile_point){ front, 0.0f };
        for (int i = 0; i <= 16; ++i)
        {
            f32 a = (f32)i / 16.0f * 1.5707963f;
            profile[n++] = (geo_profile_point){ back + radius - radius * sinf(a), radius - radius * cosf(a) };
        }
        profile[n++] = (geo_profile_point){ back, height };
        geo_extrude(&part, profile, n, width, 30.0f);

        // One image across the width, or tiles `tile` meters wide.
        f32 length = depth - radius + 1.5707963f * radius + (height - radius);
        f32 su = tile > 0.0f ? width / tile : 1.0f, sv = tile > 0.0f ? length / tile : length / width;
        for (uint32 i = 0; i < part.vertex_count; ++i)
        {
            part.vertices[i].uv[0] *= su;
            part.vertices[i].uv[1] *= sv;
        }
    }
    else
    {
        // A cylinder with a small bevel round its top edge.
        f32 r = 0.5f * width, bevel = fminf(0.006f, 0.25f * fminf(r, height));
        geo_profile_point profile[] = { { 0, 0 }, { r, 0 }, { r, height - bevel }, { r - bevel, height }, { 0, height } };
        geo_lathe(&part, profile, 5, 96, -180.0f, 180.0f, 30.0f, 0.0f, 0.0f);
    }

    b8 ok = build_and_place(s, name, &part, 1, hash, has_position ? position : NULL, out_result, error, error_size);
    geo_part_free(&part);
    return ok;
}

// --- Table ----------------------------------------------------------------------------

static const cmd_arg PRODUCT_ARGS[] = {
    { "name", "string", true, "the entity to put it on (made if missing): letters, digits, '_', '-'" },
    { "template", "string", false, "perfume, bottle, jar, can or dropper; or leave it out and give \"parts\" with profiles" },
    { "height", "number", false, "meters (templates: perfume 0.12, bottle 0.30, jar 0.07, can 0.122, dropper 0.11)" },
    { "width", "number", false, "meters across at the widest" },
    { "parts", "object", false, "template: {\"cap\": {\"color\": \"#c9a45c\", \"metallic\": 1, \"roughness\": 0.2}, \"body\": {\"opacity\": 0.85}}; "
                                "no template: [{\"name\", \"profile\": [[radius, height], ...] bottom to top in meters, \"color\", ...}]" },
    { "label", "object", false, "{\"image\": path to a PNG/JPG, \"part\": \"body\", \"from\": m, \"to\": m, \"arc\": degrees (150)}: "
                                "wrapped round the front, top of the image up" },
    { "position", "vec3", false, "where its base centre goes, e.g. on a pedestal's top" },
    { "segments", "number", false, "steps around (default 96)" },
};

static const cmd_arg BACKDROP_ARGS[] = {
    { "kind", "string", false, "cyclorama (default): a floor curving up into a wall behind; or pedestal: a round plinth" },
    { "name", "string", false, "the entity (default \"backdrop\" or \"pedestal\")" },
    { "width", "number", false, "meters (cyclorama 8; pedestal diameter 0.5)" },
    { "depth", "number", false, "cyclorama: floor depth, meters (6)" },
    { "height", "number", false, "meters (cyclorama wall 4; pedestal 0.3)" },
    { "radius", "number", false, "cyclorama: the floor-to-wall curve, meters (1.2)" },
    { "color", "string", false, "\"#RRGGBB\" or [r, g, b] linear (default near black)" },
    { "roughness", "number", false, "0..1" },
    { "metallic", "number", false, "0..1" },
    { "texture", "string", false, "an image to cover it with (e.g. from Muse Image)" },
    { "texture_tile", "number", false, "meters per repeat of the texture (default: once across)" },
    { "position", "vec3", false, "where it goes (a cyclorama's floor centre; a pedestal's base centre)" },
};

static const cmd_host_command PRODUCT_COMMANDS[] = {
    { "product.create", "Builds a product model spun from a profile (a template or your own parts), with an optional label image, "
                        "and puts it on an entity. Colours take \"#RRGGBB\".",
      PRODUCT_ARGS, sizeof(PRODUCT_ARGS) / sizeof(PRODUCT_ARGS[0]), true, cmd_product_create },
    { "backdrop.create", "Builds a cyclorama (seamless floor-to-wall backdrop) or a round pedestal and puts it on an entity.",
      BACKDROP_ARGS, sizeof(BACKDROP_ARGS) / sizeof(BACKDROP_ARGS[0]), true, cmd_backdrop_create },
};

const cmd_host_command*
product_commands(uint32* out_count)
{
    *out_count = sizeof(PRODUCT_COMMANDS) / sizeof(PRODUCT_COMMANDS[0]);
    return PRODUCT_COMMANDS;
}
