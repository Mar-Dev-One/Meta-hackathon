// Tests for Text/Font.h: loading the project's fonts, glyph metrics,
// kerning, UTF-8, missing characters, and the SDF atlas. It also draws
// sample lines on the CPU, thresholding the distance field the way the text
// shader will, and writes them and each atlas as PNGs to look at:
//
//   build/Engine/text_test_out/<font>_atlas.png, <font>_sample.png

#include "Core/Image.h"
#include "Text/Font.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                       \
    do {                                                                  \
        if (!(cond))                                                      \
        {                                                                 \
            printf("FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            ++failures;                                                   \
        }                                                                 \
    } while (0)

// --- Drawing on the CPU, as the shader will --------------------------------------------------

typedef struct canvas
{
    int    w, h;
    uint8* rgb;   // rows top to bottom
} canvas;

static f32
sample(const font* f, f32 u, f32 v)
{
    // Bilinear, in atlas pixels.
    int x0 = (int)floorf(u - 0.5f), y0 = (int)floorf(v - 0.5f);
    f32 fx = u - 0.5f - (f32)x0, fy = v - 0.5f - (f32)y0;
    f32 c[2][2];
    for (int j = 0; j < 2; ++j)
        for (int i = 0; i < 2; ++i)
        {
            int x = x0 + i < 0 ? 0 : x0 + i >= FONT_ATLAS_SIZE ? FONT_ATLAS_SIZE - 1 : x0 + i;
            int y = y0 + j < 0 ? 0 : y0 + j >= FONT_ATLAS_SIZE ? FONT_ATLAS_SIZE - 1 : y0 + j;
            c[j][i] = f->atlas[(size_t)y * FONT_ATLAS_SIZE + x] / 255.0f;
        }
    return (c[0][0] * (1 - fx) + c[0][1] * fx) * (1 - fy) + (c[1][0] * (1 - fx) + c[1][1] * fx) * fy;
}

// One line of `text` at `px` pixels, its baseline at y; returns its width.
static f32
draw_line(canvas* cv, font* f, const char* text, f32 px, f32 x, f32 baseline, const uint8 color[3])
{
    f32    k     = px / FONT_SDF_PX;
    // Half a screen pixel, in the stored distance's 0..1 units: the anti-aliased edge's width.
    f32    edge  = 0.5f * (128.0f / FONT_SDF_PADDING) / 255.0f / k;
    f32    pen   = x;
    uint32 prev  = 0;
    for (uint32 cp; (cp = utf8_next(&text)) != 0; prev = cp)
    {
        if (prev)
            pen += font_kerning(f, prev, cp) * k;
        const font_glyph* g = font_glyph_get(f, cp);
        if (!g)
            break;
        f32 gx = pen + g->x_offset * k, gy = baseline + g->y_offset * k;
        for (int py = (int)gy; py < (int)ceilf(gy + g->h * k); ++py)
            for (int px_ = (int)gx; px_ < (int)ceilf(gx + g->w * k); ++px_)
            {
                if (px_ < 0 || py < 0 || px_ >= cv->w || py >= cv->h)
                    continue;
                f32 u = g->x + ((f32)px_ + 0.5f - gx) / k, v = g->y + ((f32)py + 0.5f - gy) / k;
                if (u < g->x || v < g->y || u > g->x + g->w || v > g->y + g->h)
                    continue;
                f32 d = sample(f, u, v);
                f32 a = (d - (0.5f - edge)) / (2.0f * edge);
                a     = a < 0 ? 0 : a > 1 ? 1 : a * a * (3 - 2 * a);
                uint8* out = &cv->rgb[((size_t)py * cv->w + px_) * 3];
                for (int c = 0; c < 3; ++c)
                    out[c] = (uint8)(out[c] + (color[c] - out[c]) * a);
            }
        pen += g->advance * k;
    }
    return pen - x;
}

static b8
write_rgb_png(const canvas* cv, const char* path)
{
    uint8* flipped = malloc((size_t)cv->w * cv->h * 3);   // image_encode_png() wants rows bottom-up
    for (int y = 0; y < cv->h; ++y)
        memcpy(&flipped[(size_t)y * cv->w * 3], &cv->rgb[(size_t)(cv->h - 1 - y) * cv->w * 3], (size_t)cv->w * 3);
    size_t size = 0;
    uint8* png  = image_encode_png(flipped, (uint16)cv->w, (uint16)cv->h, 3, &size);
    free(flipped);
    FILE* file = png ? fopen(path, "wb") : NULL;
    b8    ok   = file && fwrite(png, 1, size, file) == size;
    if (file)
        fclose(file);
    free(png);
    return ok;
}

// --- Tests ---------------------------------------------------------------------------------

static void
test_utf8(void)
{
    const char* s = "A\xC3\xA9\xE2\x82\xAC\xF0\x9F\x98\x80\xFFz";   // A é € 😀 (bad byte) z
    CHECK(utf8_next(&s) == 'A');
    CHECK(utf8_next(&s) == 0xE9);
    CHECK(utf8_next(&s) == 0x20AC);
    CHECK(utf8_next(&s) == 0x1F600);
    CHECK(utf8_next(&s) == 0xFFFD);
    CHECK(utf8_next(&s) == 'z');
    CHECK(utf8_next(&s) == 0);
}

typedef struct font_case
{
    const char* name;
    const char* file;
    f32         av_units;   // the font's own "AV" kerning, in font units (fontTools)
} font_case;

static const font_case FONTS[] = {
    { "serif", "PlayfairDisplay.ttf", -50 },
    { "sans", "Montserrat-Regular.ttf", -36 },
    { "sans_bold", "Montserrat-SemiBold.ttf", -37 },
    { "condensed", "Oswald.ttf", -39 },
    { "script", "GreatVibes-Regular.ttf", 0 },
};

static void
test_font(const font_case* fc, b8* kerned)
{
    char path[1024], error[256];
    snprintf(path, sizeof(path), "%s/%s", FONT_DIR, fc->file);
    font f;
    if (!font_load(&f, fc->name, path, error, sizeof(error)))
    {
        printf("FAILED %s: %s\n", fc->name, error);
        ++failures;
        return;
    }
    CHECK(f.ascent > 0 && f.descent < 0);

    const font_glyph* a = font_glyph_get(&f, 'A');
    CHECK(a && a->w > 0 && a->h > 0 && a->advance > 0 && a->y_offset < 0);
    CHECK(font_glyph_get(&f, 'A') == a);   // made once
    const font_glyph* space = font_glyph_get(&f, ' ');
    CHECK(space && space->w == 0 && space->advance > 0);
    CHECK(font_glyph_get(&f, 0x4E2D) == font_glyph_get(&f, '?'));   // a CJK character none of these fonts has
    // Kerning comes from <font>.kern.json (scripts/font_kerning.py): the values the font itself gives.
    CHECK(f.kerning_count > 0);
    f32 av = font_kerning(&f, 'A', 'V') / f.scale, to = font_kerning(&f, 'T', 'o') / f.scale;
    CHECK(fabsf(av - fc->av_units) < 0.01f);
    CHECK(to < 0.0f);
    CHECK(font_kerning(&f, 'A', 'A') == 0.0f || f.kerning_count > 0);
    printf("  %-10s kerning: %u pairs, AV %+.0f, To %+.0f (font units)\n", fc->name, f.kerning_count, av, to);
    if (av < 0.0f)
        *kerned = true;

    // Everything printable in ASCII and Latin-1 fits, with room to spare.
    for (uint32 cp = 32; cp < 127; ++cp)
        CHECK(font_glyph_get(&f, cp) != NULL);
    for (uint32 cp = 0xC0; cp < 0x100; ++cp)
        CHECK(font_glyph_get(&f, cp) != NULL);
    printf("  %-10s %3u glyphs, atlas rows used to y = %u of %d\n", fc->name, f.glyph_count, f.shelf_y + f.shelf_h,
           FONT_ATLAS_SIZE);
    CHECK(f.shelf_y + f.shelf_h < FONT_ATLAS_SIZE / 2);

    snprintf(path, sizeof(path), "%s/%s_atlas.png", OUT_DIR, fc->name);
    CHECK(font_atlas_write_png(&f, path));

    // The same line at four sizes: sharp from small to large.
    canvas cv = { 1800, 520 };
    cv.rgb    = malloc((size_t)cv.w * cv.h * 3);
    memset(cv.rgb, 18, (size_t)cv.w * cv.h * 3);
    const uint8 white[3] = { 236, 228, 210 }, gold[3] = { 212, 175, 106 };
    const f32   sizes[]  = { 20, 40, 96, 200 };
    f32         baseline = 40;
    for (int i = 0; i < 4; ++i)
    {
        draw_line(&cv, &f, i < 3 ? "NOCTIS \xE2\x80\x94 Noir Absolu, \xC3\xA9t\xC3\xA9 2026. AVATAR Wavy" : "Noctis AV",
                  sizes[i], 20, baseline, i % 2 ? gold : white);
        baseline += sizes[i] * 1.25f + (i == 2 ? 70 : 10);
    }
    snprintf(path, sizeof(path), "%s/%s_sample.png", OUT_DIR, fc->name);
    CHECK(write_rgb_png(&cv, path));
    free(cv.rgb);
    font_destroy(&f);
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    test_utf8();
    b8 kerned = false;
    for (size_t i = 0; i < sizeof(FONTS) / sizeof(FONTS[0]); ++i)
        test_font(&FONTS[i], &kerned);
    CHECK(kerned);
    if (failures)
    {
        printf("%d check(s) failed\n", failures);
        return 1;
    }
    printf("text tests passed; pictures in %s\n", OUT_DIR);
    return 0;
}
