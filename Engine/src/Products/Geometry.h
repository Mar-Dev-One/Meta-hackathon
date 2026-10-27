#pragma once

#include "Core/Defines.h"

#include <stddef.h>

// Meshes built in code -- products spun from a profile, backdrops extruded
// from one -- and written as a glTF file, which the engine's own loader then
// reads like any other model (Scene/Model.h). Going through a file keeps
// them working across scene saves and Studio restarts, and lets the engine
// handle what it already does well: sRGB textures, alpha, several materials.
//
// Conventions: meters, +Y up, the front faces +Z (what the camera sees from
// azimuth 0). Texture coordinates are glTF's: v = 0 at the top of the image.

typedef struct geo_vertex
{
    f32 position[3];
    f32 normal[3];
    f32 uv[2];
    f32 tangent[4];   // xyz along +u, w = +1
} geo_vertex;

typedef struct geo_material
{
    f32         base_color[4];   // linear RGBA; alpha < 1 draws blended (glass)
    f32         metallic;
    f32         roughness;
    f32         emissive[3];
    const char* texture;         // base colour image, a URI relative to the .gltf; NULL = none
    b8          texture_repeat;  // tile it (a backdrop's surface); otherwise clamp at its edges (a label)
    b8          alpha_mask;      // with a texture: discard its transparent pixels (a label's cut-out shape)
    b8          double_sided;
} geo_material;

// One material's triangles.
typedef struct geo_part
{
    char         name[32];
    geo_material material;

    geo_vertex* vertices;
    uint32      vertex_count, vertex_capacity;
    uint32*     indices;
    uint32      index_count, index_capacity;
} geo_part;

void geo_part_init(geo_part* part, const char* name, const geo_material* material);
void geo_part_free(geo_part* part);

// A profile: points (radius, height) from bottom to top.
typedef struct geo_profile_point
{
    f32 r, y;
} geo_profile_point;

// Spins `profile` around +Y, `segments` steps over [angle_from, angle_to]
// degrees (0 = +Z, the front; -180 to 180 for a full turn, its seam at the
// back). Corners sharper than `sharp_degrees` get hard edges, the rest are
// smooth. A full turn whose first or last point is off the axis is closed
// with a flat disc. u runs over the angle range left to right as seen from
// the front; v over the profile's length from top (0) to bottom (1), or
// over [v_top_y, v_bottom_y] heights when they differ (a label band).
void geo_lathe(geo_part* part, const geo_profile_point* profile, uint32 count, uint32 segments,
               f32 angle_from, f32 angle_to, f32 sharp_degrees, f32 v_top_y, f32 v_bottom_y);

// Extrudes `profile` -- points (z, y), front to back -- along X from -width/2
// to width/2 (a cyclorama's floor curving into its wall). Normals face up
// and forward; u runs along X, v along the profile.
void geo_extrude(geo_part* part, const geo_profile_point* profile, uint32 count, f32 width, f32 sharp_degrees);

// Writes the parts as one glTF 2.0 model (one mesh, a primitive per part)
// with the buffers embedded. False (error filled) if it can't be written.
b8 geo_write_gltf(const char* path, const geo_part* parts, uint32 part_count, char* error, size_t error_size);
