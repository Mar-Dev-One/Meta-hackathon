#include "Font.h"

#include "Common/Json.h"
#include "Core/Image.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Static: cimgui.lib has its own stb_truetype, and two non-static copies
// would collide at link time.
#define STB_TRUETYPE_IMPLEMENTATION
#define STBTT_STATIC
#include "stb_truetype.h"

// The distance one step of the stored byte stands for: FONT_SDF_PADDING
// pixels from the edge reaches 0 (outside) or 255 (inside).
#define SDF_PIXEL_SCALE (128.0f / (f32)FONT_SDF_PADDING)

b8
font_load(font* f, const char* name, const char* path, char* error, size_t error_size)
{
    memset(f, 0, sizeof(*f));
    snprintf(f->name, sizeof(f->name), "%s", name);

    FILE* file = fopen(path, "rb");
    if (!file)
        return set_error(error, error_size, "no font file at %s", path);
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    f->file = malloc((size_t)size);
    b8 read = size > 0 && fread(f->file, 1, (size_t)size, file) == (size_t)size;
    fclose(file);

    f->info = malloc(sizeof(stbtt_fontinfo));
    if (!read || !stbtt_InitFont(f->info, f->file, stbtt_GetFontOffsetForIndex(f->file, 0)))
    {
        font_destroy(f);
        return set_error(error, error_size, "%s isn't a font stb_truetype can read", path);
    }

    f->scale = stbtt_ScaleForPixelHeight(f->info, FONT_SDF_PX);
    int ascent, descent, line_gap;
    stbtt_GetFontVMetrics(f->info, &ascent, &descent, &line_gap);
    f->ascent   = (f32)ascent * f->scale;
    f->descent  = (f32)descent * f->scale;
    f->line_gap = (f32)line_gap * f->scale;

    f->atlas  = calloc((size_t)FONT_ATLAS_SIZE * FONT_ATLAS_SIZE, 1);
    f->glyphs = malloc(FONT_MAX_GLYPHS * sizeof(*f->glyphs));
    for (int i = 0; i < 128; ++i)
        f->ascii[i] = -1;
    f->shelf_x = f->shelf_y = 1;   // a pixel of margin so neighbours never bleed into each other
    return true;
}

void
font_destroy(font* f)
{
    free(f->glyphs);
    free(f->atlas);
    free(f->info);
    free(f->file);
    memset(f, 0, sizeof(*f));
}

static font_glyph*
find(font* f, uint32 codepoint)
{
    if (codepoint < 128)
        return f->ascii[codepoint] >= 0 ? &f->glyphs[f->ascii[codepoint]] : NULL;
    for (uint32 i = 0; i < f->glyph_count; ++i)
    {
        if (f->glyphs[i].codepoint == codepoint)
            return &f->glyphs[i];
    }
    return NULL;
}

// A w x h rectangle in the atlas; false when it's full.
static b8
pack(font* f, int w, int h, uint16* x, uint16* y)
{
    if (f->shelf_x + w + 1 > FONT_ATLAS_SIZE)
    {
        f->shelf_x = 1;
        f->shelf_y += f->shelf_h + 1;
        f->shelf_h = 0;
    }
    if (f->shelf_y + h + 1 > FONT_ATLAS_SIZE || w + 2 > FONT_ATLAS_SIZE)
        return false;
    *x = f->shelf_x;
    *y = f->shelf_y;
    f->shelf_x += (uint16)(w + 1);
    if (h > f->shelf_h)
        f->shelf_h = (uint16)h;
    return true;
}

const font_glyph*
font_glyph_get(font* f, uint32 codepoint)
{
    font_glyph* glyph = find(f, codepoint);
    if (glyph)
        return glyph;

    if (f->glyph_count == FONT_MAX_GLYPHS)
        return NULL;
    int index = stbtt_FindGlyphIndex(f->info, (int)codepoint);
    if (index == 0 && codepoint != '?')
        return font_glyph_get(f, '?');   // not in the font

    int advance, left_bearing;
    stbtt_GetGlyphHMetrics(f->info, index, &advance, &left_bearing);
    font_glyph made = { .codepoint = codepoint, .advance = (f32)advance * f->scale };

    int w = 0, h = 0, x_offset = 0, y_offset = 0;
    uint8* sdf = stbtt_GetGlyphSDF(f->info, f->scale, index, FONT_SDF_PADDING, 128, SDF_PIXEL_SCALE,
                                   &w, &h, &x_offset, &y_offset);
    if (sdf)
    {
        if (!pack(f, w, h, &made.x, &made.y))
        {
            stbtt_FreeSDF(sdf, NULL);
            return NULL;
        }
        for (int row = 0; row < h; ++row)
            memcpy(&f->atlas[(size_t)(made.y + row) * FONT_ATLAS_SIZE + made.x], &sdf[(size_t)row * w], (size_t)w);
        stbtt_FreeSDF(sdf, NULL);
        made.w        = (uint16)w;
        made.h        = (uint16)h;
        made.x_offset = (f32)x_offset;
        made.y_offset = (f32)y_offset;
        f->atlas_version++;
    }

    if (codepoint < 128)
        f->ascii[codepoint] = (int32)f->glyph_count;
    f->glyphs[f->glyph_count] = made;
    return &f->glyphs[f->glyph_count++];
}

f32
font_kerning(const font* f, uint32 left, uint32 right)
{
    return (f32)stbtt_GetCodepointKernAdvance(f->info, (int)left, (int)right) * f->scale;
}

uint32
utf8_next(const char** s)
{
    const uint8* p = (const uint8*)*s;
    if (!p[0])
        return 0;

    uint32 c;
    int    extra;
    if (p[0] < 0x80)              { c = p[0];        extra = 0; }
    else if ((p[0] & 0xE0) == 0xC0) { c = p[0] & 0x1F; extra = 1; }
    else if ((p[0] & 0xF0) == 0xE0) { c = p[0] & 0x0F; extra = 2; }
    else if ((p[0] & 0xF8) == 0xF0) { c = p[0] & 0x07; extra = 3; }
    else
    {
        *s += 1;
        return 0xFFFD;
    }
    for (int i = 1; i <= extra; ++i)
    {
        if ((p[i] & 0xC0) != 0x80)
        {
            *s += i;
            return 0xFFFD;
        }
        c = (c << 6) | (p[i] & 0x3F);
    }
    *s += 1 + extra;
    return c;
}

b8
font_atlas_write_png(const font* f, const char* path)
{
    // image_encode_png() takes rows bottom-up; the atlas is top-down.
    uint8* flipped = malloc((size_t)FONT_ATLAS_SIZE * FONT_ATLAS_SIZE);
    for (int row = 0; row < FONT_ATLAS_SIZE; ++row)
        memcpy(&flipped[(size_t)row * FONT_ATLAS_SIZE], &f->atlas[(size_t)(FONT_ATLAS_SIZE - 1 - row) * FONT_ATLAS_SIZE],
               FONT_ATLAS_SIZE);
    size_t size = 0;
    uint8* png  = image_encode_png(flipped, FONT_ATLAS_SIZE, FONT_ATLAS_SIZE, 1, &size);
    free(flipped);

    FILE* file = png ? fopen(path, "wb") : NULL;
    b8    ok   = file && fwrite(png, 1, size, file) == size;
    if (file)
        ok = fclose(file) == 0 && ok;
    free(png);
    return ok;
}
