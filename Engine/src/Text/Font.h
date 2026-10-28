#pragma once

#include "Core/Defines.h"

#include <stddef.h>

// A font as signed distance fields: each glyph is drawn once, as a distance
// to its outline, into one atlas image, and can then be drawn sharp at any
// size by thresholding that distance (the text shader, Text.h). Glyphs are
// made the first time they're asked for, so any text works without picking
// a character set up front.
//
// Distances are stored as one byte per pixel: 128 is the outline itself,
// higher inside, lower outside, FONT_SDF_PADDING pixels each way covering
// the full 0..255. Every metric here is in pixels at FONT_SDF_PX (the size
// the glyphs are made at); a caller drawing at size S scales by S / FONT_SDF_PX.

#define FONT_SDF_PX      80     // the em size glyphs are drawn at: thin serif hairlines survive enlarging
#define FONT_SDF_PADDING 8      // pixels of distance field around each glyph (room for outlines, shadows)
#define FONT_ATLAS_SIZE  2048   // the atlas is FONT_ATLAS_SIZE x FONT_ATLAS_SIZE
#define FONT_MAX_GLYPHS  1024   // more than the atlas can hold at FONT_SDF_PX

struct stbtt_fontinfo;

typedef struct font_kern_pair
{
    uint32 left, right;   // codepoints
    f32    adjust;        // pixels at FONT_SDF_PX
} font_kern_pair;

typedef struct font_glyph
{
    uint32 codepoint;
    uint16 x, y, w, h;       // its rectangle in the atlas, pixels from the top-left; w = h = 0 for blank ones (space)
    f32    x_offset;         // from the pen position to the rectangle's left edge
    f32    y_offset;         // from the baseline to the rectangle's top edge (negative = above it)
    f32    advance;          // how far the pen moves after it
} font_glyph;

typedef struct font
{
    char                   name[32];
    uint8*                 file;     // the font file; stb_truetype reads from it for as long as the font lives
    struct stbtt_fontinfo* info;
    f32                    scale;    // font units to pixels at FONT_SDF_PX

    f32 ascent;     // above the baseline (positive)
    f32 descent;    // below it (negative)
    f32 line_gap;   // extra space between lines

    uint8* atlas;          // FONT_ATLAS_SIZE squared, one byte per pixel, rows top to bottom
    uint32 atlas_version;  // bumped whenever a glyph is added, so a GPU copy knows to refresh
    uint16 shelf_x, shelf_y, shelf_h;   // where the next glyph is packed (rows of glyphs, left to right)

    font_glyph* glyphs;        // FONT_MAX_GLYPHS, allocated once: pointers to glyphs stay valid
    uint32      glyph_count;
    int32       ascii[128];   // index into glyphs for codepoints below 128; -1 = not made yet

    // Kerning from the font's <name>.kern.json (scripts/font_kerning.py),
    // sorted by (left, right); none = stb_truetype's own (which misses most
    // modern fonts' GPOS kerning).
    font_kern_pair* kerning;
    uint32          kerning_count;
} font;

// Loads a TrueType / OpenType (glyf outlines) font file, and its kerning
// from <name>.kern.json beside it if there is one. False (error filled) if
// the font can't be read or isn't a font.
b8   font_load(font* f, const char* name, const char* path, char* error, size_t error_size);
void font_destroy(font* f);

// The glyph for `codepoint`, made and packed into the atlas the first time.
// A character the font doesn't have comes back as its '?'. NULL only when
// the atlas is full.
const font_glyph* font_glyph_get(font* f, uint32 codepoint);

// Extra space between two characters drawn side by side ("AV" closer
// together than "AB"), usually negative; pixels at FONT_SDF_PX.
f32 font_kerning(const font* f, uint32 left, uint32 right);

// The next character of a UTF-8 string, advancing *s past it. 0 at the end;
// a malformed byte comes back as U+FFFD and is skipped.
uint32 utf8_next(const char** s);

// The atlas as a greyscale PNG (to look at it). False if it can't be written.
b8 font_atlas_write_png(const font* f, const char* path);
