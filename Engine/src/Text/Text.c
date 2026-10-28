#include "Text.h"

#include "Common/Json.h"
#include "Core/Paths.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char* const TEXT_FONT_STYLES[TEXT_FONT_COUNT] = { "serif", "sans", "sans_bold", "condensed", "script" };
static const char* const FONT_FILES[TEXT_FONT_COUNT] = {
    "PlayfairDisplay.ttf", "Montserrat-Regular.ttf", "Montserrat-SemiBold.ttf", "Oswald.ttf", "GreatVibes-Regular.ttf",
};

static const char* const ANCHOR_NAMES[TEXT_ANCHOR_COUNT] = {
    "top_left", "top", "top_right", "left", "center", "right", "bottom_left", "bottom", "bottom_right",
};

// Quads drawn per font per frame, at most (32 items of 256 characters fit).
#define MAX_QUADS (TEXT_MAX_ITEMS * TEXT_MAX_LENGTH)

typedef struct text_vertex
{
    f32 position[2];   // normalized device coordinates
    f32 uv[2];         // in the atlas
    f32 color[4];
} text_vertex;

// The distance field thresholded at the outline, softened over about one
// screen pixel (fwidth), so text is crisp at every size.
static const char* VERTEX_SHADER =
    "#version 460 core\n"
    "layout(location = 0) in vec2 in_position;\n"
    "layout(location = 1) in vec2 in_uv;\n"
    "layout(location = 2) in vec4 in_color;\n"
    "out vec2 v_uv;\n"
    "out vec4 v_color;\n"
    "void main()\n"
    "{\n"
    "    v_uv        = in_uv;\n"
    "    v_color     = in_color;\n"
    "    gl_Position = vec4(in_position, 0.0, 1.0);\n"
    "}\n";

static const char* FRAGMENT_SHADER =
    "#version 460 core\n"
    "in vec2 v_uv;\n"
    "in vec4 v_color;\n"
    "uniform sampler2D u_atlas;\n"
    "out vec4 frag_color;\n"
    "void main()\n"
    "{\n"
    "    float d = texture(u_atlas, v_uv).r;\n"
    "    float w = max(fwidth(d) * 0.75, 1e-4);\n"
    "    float a = smoothstep(0.5 - w, 0.5 + w, d);\n"
    "    frag_color = vec4(v_color.rgb, v_color.a * a);\n"
    "}\n";

// --- Items -----------------------------------------------------------------------------

const char*
text_anchor_name(text_anchor anchor)
{
    return (uint32)anchor < TEXT_ANCHOR_COUNT ? ANCHOR_NAMES[anchor] : NULL;
}

void
text_layer_init(text_layer* t)
{
    memset(t, 0, sizeof(*t));
    t->fonts = calloc(TEXT_FONT_COUNT, sizeof(*t->fonts));
    for (int i = 0; i < TEXT_FONT_COUNT; ++i)
    {
        t->fonts[i].style = TEXT_FONT_STYLES[i];
        t->fonts[i].file  = FONT_FILES[i];
    }
}

void
text_layer_destroy(text_layer* t)
{
    for (int i = 0; t->fonts && i < TEXT_FONT_COUNT; ++i)
    {
        if (t->fonts[i].texture)
            rhi_texture_destroy(t->fonts[i].texture);
        if (t->fonts[i].loaded)
            font_destroy(&t->fonts[i].font);
    }
    free(t->fonts);
    if (t->shader)
        rhi_shader_destroy(t->shader);
    if (t->vertices)
        rhi_buffer_destroy(t->vertices);
    if (t->indices)
        rhi_buffer_destroy(t->indices);
    memset(t, 0, sizeof(*t));
}

void
text_layer_clear(text_layer* t)
{
    t->count = 0;
}

text_item*
text_find(text_layer* t, const char* name)
{
    for (uint32 i = 0; i < t->count; ++i)
    {
        if (strcmp(t->items[i].name, name) == 0)
            return &t->items[i];
    }
    return NULL;
}

void
text_item_defaults(text_item* item, const char* name)
{
    *item = (text_item){
        .font = "sans", .size = 0.06f, .anchor = TEXT_CENTER, .color = { 1, 1, 1, 1 },
        .opacity = 1.0f, .scale = 1.0f, .line_spacing = 1.0f, .visible = true,
    };
    snprintf(item->name, sizeof(item->name), "%s", name);
}

text_item*
text_add(text_layer* t, const char* name)
{
    if (text_find(t, name) || t->count == TEXT_MAX_ITEMS || !name[0] || strlen(name) >= ENTITY_NAME_MAX)
        return NULL;
    text_item* item = &t->items[t->count++];
    text_item_defaults(item, name);
    return item;
}

b8
text_remove(text_layer* t, const char* name)
{
    text_item* item = text_find(t, name);
    if (!item)
        return false;
    uint32 index = (uint32)(item - t->items);
    memmove(&t->items[index], &t->items[index + 1], (t->count - index - 1) * sizeof(*item));
    t->count--;
    return true;
}

static text_font*
find_font(text_layer* t, const char* style)
{
    for (int i = 0; i < TEXT_FONT_COUNT; ++i)
    {
        if (strcmp(t->fonts[i].style, style) == 0)
            return &t->fonts[i];
    }
    return NULL;
}

b8
text_item_from_json(text_layer* t, text_item* item, const cJSON* json, b8 strict, char* error, size_t error_size)
{
    static const char* const KEYS[] = { "name", "text", "font", "size", "anchor", "offset", "color", "opacity",
                                        "tracking", "scale", "line_spacing", "visible" };
    const cJSON* key;
    cJSON_ArrayForEach(key, json)
    {
        b8 known = false;
        for (size_t i = 0; i < sizeof(KEYS) / sizeof(KEYS[0]); ++i)
            known = known || strcmp(key->string, KEYS[i]) == 0;
        if (strict && !known)
            return set_error(error, error_size, "a text doesn't take \"%s\"", key->string);
    }

    // Read into a copy, so a bad key changes nothing.
    text_item next = *item;
    const char *text = NULL, *font = NULL, *anchor = NULL, *color = NULL;
    if (arg_string(json, "font", &font, error, error_size) < 0 || arg_string(json, "anchor", &anchor, error, error_size) < 0
        || arg_string(json, "color", &color, error, error_size) < 0
        || arg_number(json, "size", 0.005f, 1.0f, &next.size, error, error_size) < 0
        || arg_number(json, "opacity", 0.0f, 1.0f, &next.opacity, error, error_size) < 0
        || arg_number(json, "tracking", -0.5f, 2.0f, &next.tracking, error, error_size) < 0
        || arg_number(json, "scale", 0.01f, 20.0f, &next.scale, error, error_size) < 0
        || arg_number(json, "line_spacing", 0.5f, 4.0f, &next.line_spacing, error, error_size) < 0
        || arg_bool(json, "visible", &next.visible, error, error_size) < 0)
        return false;

    // The text may be empty (a title not shown yet), so it isn't read with arg_string().
    const cJSON* text_json = cJSON_GetObjectItemCaseSensitive(json, "text");
    if (text_json)
    {
        if (!cJSON_IsString(text_json) || strlen(text_json->valuestring) >= TEXT_MAX_LENGTH)
            return set_error(error, error_size, "\"text\" must be a string of at most %d bytes", TEXT_MAX_LENGTH - 1);
        text = text_json->valuestring;
    }
    if (font && !find_font(t, font))
        return set_error(error, error_size, "\"font\" must be serif, sans, sans_bold, condensed or script");
    if (anchor)
    {
        int found = -1;
        for (int i = 0; i < TEXT_ANCHOR_COUNT; ++i)
            found = strcmp(anchor, ANCHOR_NAMES[i]) == 0 ? i : found;
        if (found < 0)
            return set_error(error, error_size, "\"anchor\" must be top_left, top, top_right, left, center, right, "
                                                "bottom_left, bottom or bottom_right");
        next.anchor = (text_anchor)found;
    }
    if (color && !parse_hex_color(color, next.color, false))
        return set_error(error, error_size, "\"color\" must be \"#RRGGBB\" or \"#RRGGBBAA\"");
    const cJSON* offset = cJSON_GetObjectItemCaseSensitive(json, "offset");
    if (offset && (!json_read_floats(offset, next.offset, 2) || fabsf(next.offset[0]) > 2.0f || fabsf(next.offset[1]) > 2.0f))
        return set_error(error, error_size, "\"offset\" must be [x, y] in shares of the frame, -2 to 2 (+y is down)");

    if (text)
        snprintf(next.text, sizeof(next.text), "%s", text);
    if (font)
        snprintf(next.font, sizeof(next.font), "%s", font);
    *item = next;
    return true;
}

cJSON*
text_item_to_json(const text_item* item)
{
    char color[16];
    snprintf(color, sizeof(color), "#%02X%02X%02X%02X", (int)lroundf(item->color[0] * 255), (int)lroundf(item->color[1] * 255),
             (int)lroundf(item->color[2] * 255), (int)lroundf(item->color[3] * 255));
    cJSON* json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "name", item->name);
    cJSON_AddStringToObject(json, "text", item->text);
    cJSON_AddStringToObject(json, "font", item->font);
    cJSON_AddNumberToObject(json, "size", json_round6(item->size));
    cJSON_AddStringToObject(json, "anchor", ANCHOR_NAMES[item->anchor]);
    json_add_floats(json, "offset", item->offset, 2);
    cJSON_AddStringToObject(json, "color", color);
    cJSON_AddNumberToObject(json, "opacity", json_round6(item->opacity));
    cJSON_AddNumberToObject(json, "tracking", json_round6(item->tracking));
    cJSON_AddNumberToObject(json, "scale", json_round6(item->scale));
    cJSON_AddNumberToObject(json, "line_spacing", json_round6(item->line_spacing));
    cJSON_AddBoolToObject(json, "visible", item->visible);
    return json;
}

// --- Animation --------------------------------------------------------------------------

typedef struct text_track_field
{
    const char* name;
    uint32      width;
    f32         min, max;
    size_t      offset;   // into text_item
} text_track_field;

static const text_track_field TRACK_FIELDS[] = {
    { "opacity", 1, 0.0f, 1.0f, offsetof(text_item, opacity) },
    { "scale", 1, 0.01f, 20.0f, offsetof(text_item, scale) },
    { "tracking", 1, -0.5f, 2.0f, offsetof(text_item, tracking) },
    { "size", 1, 0.005f, 1.0f, offsetof(text_item, size) },
    { "offset", 2, -2.0f, 2.0f, offsetof(text_item, offset) },
    { "color", 4, 0.0f, 1.0f, offsetof(text_item, color) },
};

static const text_track_field*
track_field(const char* name)
{
    for (size_t i = 0; name && i < sizeof(TRACK_FIELDS) / sizeof(TRACK_FIELDS[0]); ++i)
    {
        if (strcmp(name, TRACK_FIELDS[i].name) == 0)
            return &TRACK_FIELDS[i];
    }
    return NULL;
}

b8
text_track_describe(void* user, const char* field, uint32* out_width, f32* out_min, f32* out_max,
                    char* error, size_t error_size)
{
    (void)user;
    const text_track_field* f = track_field(field);
    if (!f)
        return set_error(error, error_size, "Text has no field \"%s\"; its animatable fields are: opacity, scale, "
                                            "tracking, size, offset ([x, y]), color ([r, g, b, a])", field ? field : "");
    *out_width = f->width;
    *out_min   = f->min;
    *out_max   = f->max;
    return true;
}

b8
text_track_write(void* user, const char* entity, const char* field, const f32* value, uint32 width)
{
    text_item*              item = text_find((text_layer*)user, entity);
    const text_track_field* f    = track_field(field);
    if (!item || !f || width != f->width)
        return false;
    // Keys are in range, but a bezier ease can overshoot between them.
    f32* out = (f32*)((uint8*)item + f->offset);
    for (uint32 i = 0; i < width; ++i)
        out[i] = glm_clamp(value[i], f->min, f->max);
    return true;
}

// --- Layout ----------------------------------------------------------------------------

static font*
loaded_font(text_font* tf)
{
    if (!tf->loaded && !tf->failed)
    {
        char  relative[128], error[256];
        snprintf(relative, sizeof(relative), "fonts/%s", tf->file);
        char* path = project_path(relative);
        tf->loaded = path && font_load(&tf->font, tf->style, path, error, sizeof(error));
        tf->failed = !tf->loaded;
        if (tf->failed)
            LOG_ERROR("text: the %s font didn't load: %s\n", tf->style, path ? error : relative);
        free(path);
    }
    return tf->loaded ? &tf->font : NULL;
}

// One line's width in pixels at scale k (FONT_SDF_PX pixels per k).
static f32
line_width(font* f, const char* line, const char* end, f32 k, f32 tracking_px)
{
    f32    width = 0.0f;
    uint32 prev  = 0;
    int    count = 0;
    for (const char* s = line; s < end;)
    {
        uint32 cp = utf8_next(&s);
        const font_glyph* g = font_glyph_get(f, cp);
        if (!g)
            break;
        width += (prev ? font_kerning(f, prev, cp) * k : 0.0f) + g->advance * k;
        prev = cp;
        ++count;
    }
    return width + tracking_px * (f32)(count > 1 ? count - 1 : 0);
}

typedef struct quad_sink
{
    text_vertex* vertices;
    uint32       count, capacity;   // in quads
} quad_sink;

// Lays the item out in a width x height frame: its block's top-left and
// size into out_box, and (with a sink) one quad per visible glyph.
static b8
lay_out(text_layer* t, const text_item* item, f32 width, f32 height, quad_sink* sink, f32 out_box[4])
{
    text_font* tf = find_font(t, item->font);
    font*      f  = tf ? loaded_font(tf) : NULL;
    if (!f)
        return false;

    f32 px      = item->size * item->scale * height;
    f32 k       = px / FONT_SDF_PX;
    f32 track   = item->tracking * px;
    f32 line_h  = (f->ascent - f->descent + f->line_gap) * k * item->line_spacing;

    // The lines and the block's size.
    const char* starts[32];
    const char* ends[32];
    f32         widths[32];
    int         lines = 0;
    f32         block_w = 0.0f;
    for (const char* s = item->text; lines < 32;)
    {
        const char* end = strchr(s, '\n');
        if (!end)
            end = s + strlen(s);
        starts[lines] = s;
        ends[lines]   = end;
        widths[lines] = line_width(f, s, end, k, track);
        block_w       = fmaxf(block_w, widths[lines]);
        ++lines;
        if (!*end)
            break;
        s = end + 1;
    }
    f32 block_h = (f->ascent - f->descent) * k + (f32)(lines - 1) * line_h;

    // The anchor's column and row: 0, 0.5 or 1 across and down the frame.
    f32 col = (f32)(item->anchor % 3) * 0.5f, row = (f32)(item->anchor / 3) * 0.5f;
    f32 left = col * width + item->offset[0] * width - col * block_w;
    f32 top  = row * height + item->offset[1] * height - row * block_h;
    out_box[0] = left;
    out_box[1] = top;
    out_box[2] = block_w;
    out_box[3] = block_h;
    if (!sink)
        return true;

    f32 alpha = item->color[3] * item->opacity;
    for (int l = 0; l < lines; ++l)
    {
        f32    pen      = left + (block_w - widths[l]) * col;   // lines align the way the anchor does
        f32    baseline = top + f->ascent * k + (f32)l * line_h;
        uint32 prev     = 0;
        for (const char* s = starts[l]; s < ends[l];)
        {
            uint32 cp = utf8_next(&s);
            const font_glyph* g = font_glyph_get(f, cp);
            if (!g)
                break;
            if (prev)
                pen += font_kerning(f, prev, cp) * k;
            if (g->w && sink->count < sink->capacity)
            {
                f32 x0 = pen + g->x_offset * k, y0 = baseline + g->y_offset * k;
                f32 x1 = x0 + g->w * k, y1 = y0 + g->h * k;
                f32 u0 = (f32)g->x / FONT_ATLAS_SIZE, v0 = (f32)g->y / FONT_ATLAS_SIZE;
                f32 u1 = (f32)(g->x + g->w) / FONT_ATLAS_SIZE, v1 = (f32)(g->y + g->h) / FONT_ATLAS_SIZE;
                // Pixels (y down) to normalized device coordinates (y up).
                f32 nx0 = x0 / width * 2.0f - 1.0f, nx1 = x1 / width * 2.0f - 1.0f;
                f32 ny0 = 1.0f - y0 / height * 2.0f, ny1 = 1.0f - y1 / height * 2.0f;
                text_vertex* v = &sink->vertices[sink->count++ * 4];
                v[0] = (text_vertex){ { nx0, ny0 }, { u0, v0 }, { item->color[0], item->color[1], item->color[2], alpha } };
                v[1] = (text_vertex){ { nx1, ny0 }, { u1, v0 }, { item->color[0], item->color[1], item->color[2], alpha } };
                v[2] = (text_vertex){ { nx1, ny1 }, { u1, v1 }, { item->color[0], item->color[1], item->color[2], alpha } };
                v[3] = (text_vertex){ { nx0, ny1 }, { u0, v1 }, { item->color[0], item->color[1], item->color[2], alpha } };
            }
            pen += g->advance * k + track;
            prev = cp;
        }
    }
    return true;
}

b8
text_measure(text_layer* t, const text_item* item, f32 width, f32 height, f32 out_box[4])
{
    return lay_out(t, item, width, height, NULL, out_box);
}

// --- Drawing ---------------------------------------------------------------------------

static b8
make_gpu_objects(text_layer* t)
{
    if (t->shader)
        return true;
    t->shader = rhi_shader_create((rhi_shader_desc){ .vertex_src = VERTEX_SHADER, .fragment_src = FRAGMENT_SHADER });
    if (!t->shader)
    {
        LOG_ERROR("text: the text shader didn't compile\n");
        return false;
    }

    static const rhi_vertex_attribute ATTRIBUTES[] = {
        { 0, 2, offsetof(text_vertex, position) },
        { 1, 2, offsetof(text_vertex, uv) },
        { 2, 4, offsetof(text_vertex, color) },
    };
    rhi_vertex_layout layout = { ATTRIBUTES, 3, sizeof(text_vertex) };
    t->vertices = rhi_vertex_buffer_create(NULL, (uint64)MAX_QUADS * 4 * sizeof(text_vertex), &layout, RHI_USAGE_DYNAMIC);

    // Two triangles per quad, for every quad there could be.
    uint32* indices = malloc((size_t)MAX_QUADS * 6 * sizeof(uint32));
    for (uint32 q = 0; q < MAX_QUADS; ++q)
    {
        uint32 v = q * 4;
        uint32 quad[6] = { v, v + 1, v + 2, v, v + 2, v + 3 };
        memcpy(&indices[q * 6], quad, sizeof(quad));
    }
    t->indices = rhi_index_buffer_create(indices, (uint64)MAX_QUADS * 6 * sizeof(uint32), RHI_USAGE_STATIC);
    free(indices);
    return true;
}

// The font's atlas on the GPU, re-uploaded when glyphs were added.
static void
upload_atlas(text_font* tf)
{
    if (tf->texture && tf->texture_version == tf->font.atlas_version)
        return;
    if (tf->texture)
        rhi_texture_destroy(tf->texture);

    // RGBA8: the RHI has no one-channel format. The distance goes in every channel.
    // No mipmaps: small text samples the coarse levels, where neighbouring
    // glyphs (1 px apart) average into each other and eat strokes away
    // ("ABSOLU" drawn as "A3SOLU" at 15 px). Full resolution plus the
    // shader's fwidth smoothing stays clean.
    size_t pixels = (size_t)FONT_ATLAS_SIZE * FONT_ATLAS_SIZE;
    uint8* rgba   = malloc(pixels * 4);
    for (size_t i = 0; i < pixels; ++i)
        memset(&rgba[i * 4], tf->font.atlas[i], 4);
    tf->texture = rhi_texture_create((rhi_texture_desc){
        .width = FONT_ATLAS_SIZE, .height = FONT_ATLAS_SIZE, .format = RHI_FORMAT_RGBA8,
        .filter = RHI_FILTER_LINEAR, .wrap = RHI_WRAP_CLAMP_TO_EDGE, .pixels = rgba, .generate_mipmaps = false,
    });
    free(rgba);
    tf->texture_version = tf->font.atlas_version;
}

void
text_layer_draw(text_layer* t, uint16 width, uint16 height)
{
    b8 any = false;
    for (uint32 i = 0; i < t->count; ++i)
        any = any || (t->items[i].visible && t->items[i].text[0] && t->items[i].opacity > 0.0f);
    if (!any || !make_gpu_objects(t))
        return;

    quad_sink sink = { .vertices = malloc((size_t)MAX_QUADS * 4 * sizeof(text_vertex)), .capacity = MAX_QUADS };
    rhi_set_render_state((rhi_render_state){ .cull_back_faces = false, .blend_enabled = true, .depth_write = false });
    rhi_shader_bind(t->shader);
    rhi_shader_set_int(t->shader, "u_atlas", 0);

    // One draw per font: its items' glyphs, then its atlas (uploaded after
    // layout, which may have added glyphs).
    for (int fi = 0; fi < TEXT_FONT_COUNT; ++fi)
    {
        sink.count = 0;
        for (uint32 i = 0; i < t->count; ++i)
        {
            const text_item* item = &t->items[i];
            f32              box[4];
            if (item->visible && item->text[0] && item->opacity > 0.0f && strcmp(item->font, t->fonts[fi].style) == 0)
                lay_out(t, item, width, height, &sink, box);
        }
        if (!sink.count)
            continue;
        upload_atlas(&t->fonts[fi]);
        rhi_buffer_update(t->vertices, sink.vertices, (uint64)sink.count * 4 * sizeof(text_vertex), 0);
        rhi_texture_bind(t->fonts[fi].texture, 0);
        rhi_draw_indexed(t->vertices, t->indices, sink.count * 6);
    }

    free(sink.vertices);
    rhi_set_render_state(rhi_render_state_default());
}
