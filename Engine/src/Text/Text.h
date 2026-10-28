#pragma once

#include "Core/Defines.h"
#include "RHI/RHI.h"
#include "World/Components.h"
#include "Font.h"

#include "cJSON.h"

#include <stddef.h>

// Titles drawn over the finished picture: after the scene is tone-mapped,
// into the same frame, so they're in every shot frame the critic looks at.
// Each item is laid out relative to the frame -- its size a share of the
// frame's height, its position an anchor plus an offset in shares of the
// frame -- so a 640-wide preview and a 1920-wide render look the same.
//
// Colours are sRGB, as they'll be seen: text is drawn after tone mapping.
// Fonts are named by style (TEXT_FONTS), loaded from the project's fonts/
// folder the first time they're used, with their kerning (Font.h).

#define TEXT_MAX_ITEMS  32
#define TEXT_MAX_LENGTH 256

typedef enum text_anchor
{
    TEXT_TOP_LEFT, TEXT_TOP, TEXT_TOP_RIGHT,
    TEXT_LEFT, TEXT_CENTER, TEXT_RIGHT,
    TEXT_BOTTOM_LEFT, TEXT_BOTTOM, TEXT_BOTTOM_RIGHT,
    TEXT_ANCHOR_COUNT
} text_anchor;

typedef struct text_item
{
    char        name[ENTITY_NAME_MAX];
    char        text[TEXT_MAX_LENGTH];   // UTF-8; "\n" starts a new line
    char        font[32];                // a TEXT_FONTS style: serif, sans, sans_bold, condensed, script
    f32         size;                    // the font's em as a share of the frame's height
    text_anchor anchor;                  // the frame point it hangs from, and how its lines align
    f32         offset[2];               // from the anchor, in shares of the frame's width and height (+y down)
    f32         color[4];                // sRGB and alpha, 0..1
    f32         opacity;                 // times the colour's alpha
    f32         tracking;                // extra space between letters, in ems
    f32         scale;                   // times size
    f32         line_spacing;            // times the font's line height
    b8          visible;
} text_item;

typedef struct text_font
{
    const char* style;
    const char* file;           // under the project's fonts/
    font        font;
    b8          loaded, failed;
    rhi_texture texture;        // the atlas on the GPU
    uint32      texture_version;
} text_font;

typedef struct text_layer
{
    text_item items[TEXT_MAX_ITEMS];
    uint32    count;

    text_font* fonts;   // TEXT_FONT_COUNT, in TEXT_FONTS' order

    // Made on the first draw (needs the GL context).
    rhi_shader shader;
    rhi_buffer vertices, indices;
} text_layer;

extern const char* const TEXT_FONT_STYLES[];
#define TEXT_FONT_COUNT 5

void text_layer_init(text_layer* t);
void text_layer_destroy(text_layer* t);   // while the GL context is alive
void text_layer_clear(text_layer* t);     // every item removed; fonts stay loaded

// The item called `name`, or NULL.
text_item* text_find(text_layer* t, const char* name);

// The defaults: sans, 6% of the frame's height, centred, white, visible.
void text_item_defaults(text_item* item, const char* name);

// A new item with the defaults, NULL if the name is taken or the layer is full.
text_item* text_add(text_layer* t, const char* name);
b8         text_remove(text_layer* t, const char* name);

// Writes the keys present in `json` into `item`, all-or-nothing: text,
// font, size, anchor, offset, color ("#RRGGBB" or "#RRGGBBAA"), opacity,
// tracking, scale, line_spacing, visible. Unknown keys are an error when
// `strict`.
b8     text_item_from_json(text_layer* t, text_item* item, const cJSON* json, b8 strict, char* error, size_t error_size);
cJSON* text_item_to_json(const text_item* item);

// The item's block in pixels in a width x height frame: its top-left
// corner and size. False if its font can't load.
b8 text_measure(text_layer* t, const text_item* item, f32 width, f32 height, f32 out_box[4]);

// Draws every visible item into the bound framebuffer, which is width x
// height pixels (its viewport already set). Leaves the default render state.
void text_layer_draw(text_layer* t, uint16 width, uint16 height);

// anchor names: "top_left", "top", ..., "center", ..., "bottom_right".
const char* text_anchor_name(text_anchor anchor);

// The timeline's hooks for animating titles as component "Text" (user = the
// text_layer; Timeline.h, timeline_custom_target). Fields: opacity, scale,
// tracking, size (one number each), offset ([x, y]) and color ([r, g, b, a],
// sRGB 0..1). Values are kept in each field's range.
b8 text_track_describe(void* user, const char* field, uint32* out_width, f32* out_min, f32* out_max,
                       char* error, size_t error_size);
b8 text_track_write(void* user, const char* entity, const char* field, const f32* value, uint32 width);
