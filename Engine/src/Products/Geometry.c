#include "Geometry.h"

#include "Common/Json.h"
#include "Core/Encoding.h"
#include "Core/FileIO.h"

#include "cJSON.h"

#include <cglm/cglm.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DEG_TO_RAD (3.14159265358979f / 180.0f)

void
geo_part_init(geo_part* part, const char* name, const geo_material* material)
{
    memset(part, 0, sizeof(*part));
    snprintf(part->name, sizeof(part->name), "%s", name);
    part->material = *material;
}

void
geo_part_free(geo_part* part)
{
    free(part->vertices);
    free(part->indices);
    memset(part, 0, sizeof(*part));
}

static uint32
add_vertex(geo_part* part, const f32 position[3], const f32 normal[3], f32 u, f32 v, const f32 tangent[3])
{
    if (part->vertex_count == part->vertex_capacity)
    {
        part->vertex_capacity = part->vertex_capacity ? part->vertex_capacity * 2 : 256;
        part->vertices        = realloc(part->vertices, part->vertex_capacity * sizeof(*part->vertices));
    }
    geo_vertex* out = &part->vertices[part->vertex_count];
    memcpy(out->position, position, sizeof(out->position));
    memcpy(out->normal, normal, sizeof(out->normal));
    out->uv[0] = u;
    out->uv[1] = v;
    memcpy(out->tangent, tangent, 3 * sizeof(f32));
    out->tangent[3] = 1.0f;
    return part->vertex_count++;
}

// A triangle wound counter-clockwise as seen from the side its vertices'
// normals face, whatever order a, b, c come in.
static void
add_triangle(geo_part* part, uint32 a, uint32 b, uint32 c)
{
    const geo_vertex* v = part->vertices;
    vec3 ab, ac, face, normal;
    glm_vec3_sub((f32*)v[b].position, (f32*)v[a].position, ab);
    glm_vec3_sub((f32*)v[c].position, (f32*)v[a].position, ac);
    glm_vec3_cross(ab, ac, face);
    if (glm_vec3_norm2(face) < 1e-14f)
        return;   // degenerate: where a profile meets the axis
    glm_vec3_add((f32*)v[a].normal, (f32*)v[b].normal, normal);
    glm_vec3_add(normal, (f32*)v[c].normal, normal);
    if (glm_vec3_dot(face, normal) < 0.0f)
    {
        uint32 t = b;
        b        = c;
        c        = t;
    }

    if (part->index_count + 3 > part->index_capacity)
    {
        part->index_capacity = part->index_capacity ? part->index_capacity * 2 : 768;
        part->indices        = realloc(part->indices, part->index_capacity * sizeof(*part->indices));
    }
    part->indices[part->index_count++] = a;
    part->indices[part->index_count++] = b;
    part->indices[part->index_count++] = c;
}

// --- Profiles --------------------------------------------------------------------------

// The outward 2D normal of segment p -> q: the direction rotated a quarter
// turn clockwise, so a profile going up has its normal pointing out.
static void
segment_normal(geo_profile_point p, geo_profile_point q, f32 out[2])
{
    f32 dx = q.r - p.r, dy = q.y - p.y;
    f32 length = sqrtf(dx * dx + dy * dy);
    out[0] = length > 0.0f ? dy / length : 1.0f;
    out[1] = length > 0.0f ? -dx / length : 0.0f;
}

// The normals a segment's two ends use: smooth at gentle corners (shared with
// the neighbouring segment), the segment's own at sharp ones.
static void
end_normals(const geo_profile_point* profile, uint32 count, uint32 segment, f32 sharp_degrees,
            f32 start[2], f32 end[2])
{
    f32 own[2], before[2], after[2];
    segment_normal(profile[segment], profile[segment + 1], own);
    f32 cos_sharp = cosf(sharp_degrees * DEG_TO_RAD);

    start[0] = own[0];
    start[1] = own[1];
    if (segment > 0)
    {
        segment_normal(profile[segment - 1], profile[segment], before);
        if (before[0] * own[0] + before[1] * own[1] > cos_sharp)
        {
            start[0] = before[0] + own[0];
            start[1] = before[1] + own[1];
        }
    }
    end[0] = own[0];
    end[1] = own[1];
    if (segment + 2 < count)
    {
        segment_normal(profile[segment + 1], profile[segment + 2], after);
        if (after[0] * own[0] + after[1] * own[1] > cos_sharp)
        {
            end[0] = after[0] + own[0];
            end[1] = after[1] + own[1];
        }
    }
    glm_vec2_normalize(start);
    glm_vec2_normalize(end);
}

// Each point's distance along the profile from its first point.
static f32
profile_lengths(const geo_profile_point* profile, uint32 count, f32* out)
{
    out[0] = 0.0f;
    for (uint32 i = 1; i < count; ++i)
        out[i] = out[i - 1] + hypotf(profile[i].r - profile[i - 1].r, profile[i].y - profile[i - 1].y);
    return out[count - 1];
}

// --- Lathe -----------------------------------------------------------------------------

static void
lathe_ring(geo_part* part, geo_profile_point p, const f32 n[2], f32 v, uint32 segments, f32 from, f32 to)
{
    for (uint32 k = 0; k <= segments; ++k)
    {
        f32 u = (f32)k / (f32)segments;
        f32 a = glm_lerp(from, to, u) * DEG_TO_RAD;
        f32 s = sinf(a), c = cosf(a);
        f32 position[3] = { p.r * s, p.y, p.r * c };
        f32 normal[3]   = { n[0] * s, n[1], n[0] * c };
        f32 tangent[3]  = { c, 0.0f, -s };
        add_vertex(part, position, normal, u, v, tangent);
    }
}

static void
lathe_disc(geo_part* part, geo_profile_point edge, f32 normal_y, uint32 segments)
{
    f32    normal[3]  = { 0.0f, normal_y, 0.0f };
    f32    tangent[3] = { 1.0f, 0.0f, 0.0f };
    f32    centre[3]  = { 0.0f, edge.y, 0.0f };
    uint32 middle     = add_vertex(part, centre, normal, 0.5f, 0.5f, tangent);
    uint32 first      = part->vertex_count;
    for (uint32 k = 0; k <= segments; ++k)
    {
        f32 a = ((f32)k / (f32)segments * 360.0f - 180.0f) * DEG_TO_RAD;
        f32 position[3] = { edge.r * sinf(a), edge.y, edge.r * cosf(a) };
        add_vertex(part, position, normal, 0.5f + 0.5f * sinf(a), 0.5f - 0.5f * cosf(a), tangent);
    }
    for (uint32 k = 0; k < segments; ++k)
        add_triangle(part, middle, first + k, first + k + 1);
}

void
geo_lathe(geo_part* part, const geo_profile_point* profile, uint32 count, uint32 segments,
          f32 angle_from, f32 angle_to, f32 sharp_degrees, f32 v_top_y, f32 v_bottom_y)
{
    if (count < 2 || segments < 3)
        return;

    f32* lengths = malloc(count * sizeof(f32));
    f32  total   = profile_lengths(profile, count, lengths);
    b8   by_height = fabsf(v_top_y - v_bottom_y) > 1e-6f;

    for (uint32 j = 0; j + 1 < count; ++j)
    {
        if (lengths[j + 1] - lengths[j] < 1e-7f)
            continue;   // a repeated point
        f32 n0[2], n1[2];
        end_normals(profile, count, j, sharp_degrees, n0, n1);

        f32 v0 = by_height ? (v_top_y - profile[j].y) / (v_top_y - v_bottom_y) : 1.0f - lengths[j] / total;
        f32 v1 = by_height ? (v_top_y - profile[j + 1].y) / (v_top_y - v_bottom_y) : 1.0f - lengths[j + 1] / total;

        uint32 a = part->vertex_count;
        lathe_ring(part, profile[j], n0, v0, segments, angle_from, angle_to);
        uint32 b = part->vertex_count;
        lathe_ring(part, profile[j + 1], n1, v1, segments, angle_from, angle_to);
        for (uint32 k = 0; k < segments; ++k)
        {
            add_triangle(part, a + k, a + k + 1, b + k + 1);
            add_triangle(part, a + k, b + k + 1, b + k);
        }
    }
    free(lengths);

    // A full turn left open at an end gets a flat disc there.
    if (fabsf(angle_to - angle_from) >= 359.9f)
    {
        if (profile[0].r > 1e-5f)
            lathe_disc(part, profile[0], -1.0f, segments);
        if (profile[count - 1].r > 1e-5f)
            lathe_disc(part, profile[count - 1], 1.0f, segments);
    }
}

// --- Extrusion -------------------------------------------------------------------------

void
geo_extrude(geo_part* part, const geo_profile_point* profile, uint32 count, f32 width, f32 sharp_degrees)
{
    if (count < 2)
        return;

    f32* lengths = malloc(count * sizeof(f32));
    f32  total   = profile_lengths(profile, count, lengths);
    f32  tangent[3] = { 1.0f, 0.0f, 0.0f };

    for (uint32 j = 0; j + 1 < count; ++j)
    {
        if (lengths[j + 1] - lengths[j] < 1e-7f)
            continue;
        // The profile is (z, y), so its 2D normal is (nz, ny): a floor running
        // back (z decreasing) faces up, a wall rising faces forward.
        f32 n0[2], n1[2];
        end_normals(profile, count, j, sharp_degrees, n0, n1);

        uint32 first = part->vertex_count;
        for (int end = 0; end < 2; ++end)
        {
            geo_profile_point p = profile[j + end];
            const f32*        n = end ? n1 : n0;
            f32               v = lengths[j + end] / total;
            for (int side = 0; side < 2; ++side)
            {
                f32 x           = side ? 0.5f * width : -0.5f * width;
                f32 position[3] = { x, p.y, p.r };
                f32 normal[3]   = { 0.0f, n[1], n[0] };
                add_vertex(part, position, normal, (f32)side, v, tangent);
            }
        }
        add_triangle(part, first, first + 1, first + 3);
        add_triangle(part, first, first + 3, first + 2);
    }
    free(lengths);
}

// --- glTF ------------------------------------------------------------------------------

typedef struct byte_buffer
{
    uint8* data;
    size_t size, capacity;
} byte_buffer;

static size_t
append(byte_buffer* b, const void* data, size_t size)
{
    if (b->size + size > b->capacity)
    {
        b->capacity = (b->size + size) * 2;
        b->data     = realloc(b->data, b->capacity);
    }
    size_t offset = b->size;
    memcpy(b->data + offset, data, size);
    b->size += size;
    return offset;
}

// One attribute of every vertex (`floats` wide at `offset` floats in), as
// a buffer view and accessor; returns the accessor's index.
static int
add_accessor(cJSON* views, cJSON* accessors, byte_buffer* buffer, const void* data, size_t size,
             uint32 count, int component, const char* type, int target)
{
    size_t offset = append(buffer, data, size);
    cJSON* view   = cJSON_CreateObject();
    cJSON_AddNumberToObject(view, "buffer", 0);
    cJSON_AddNumberToObject(view, "byteOffset", (double)offset);
    cJSON_AddNumberToObject(view, "byteLength", (double)size);
    cJSON_AddNumberToObject(view, "target", target);
    cJSON_AddItemToArray(views, view);

    cJSON* accessor = cJSON_CreateObject();
    cJSON_AddNumberToObject(accessor, "bufferView", cJSON_GetArraySize(views) - 1);
    cJSON_AddNumberToObject(accessor, "componentType", component);
    cJSON_AddNumberToObject(accessor, "count", count);
    cJSON_AddStringToObject(accessor, "type", type);
    cJSON_AddItemToArray(accessors, accessor);
    return cJSON_GetArraySize(accessors) - 1;
}

#define GLTF_FLOAT        5126
#define GLTF_UNSIGNED_INT 5125
#define GLTF_ARRAY        34962
#define GLTF_ELEMENTS     34963

static cJSON*
material_json(const geo_material* m, cJSON* textures, cJSON* images, cJSON* samplers)
{
    cJSON* json = cJSON_CreateObject();
    cJSON* pbr  = cJSON_AddObjectToObject(json, "pbrMetallicRoughness");
    json_add_floats(pbr, "baseColorFactor", m->base_color, 4);
    cJSON_AddNumberToObject(pbr, "metallicFactor", json_round6(m->metallic));
    cJSON_AddNumberToObject(pbr, "roughnessFactor", json_round6(m->roughness));
    if (m->emissive[0] > 0.0f || m->emissive[1] > 0.0f || m->emissive[2] > 0.0f)
        json_add_floats(json, "emissiveFactor", m->emissive, 3);

    if (m->texture)
    {
        cJSON* image = cJSON_CreateObject();
        cJSON_AddStringToObject(image, "uri", m->texture);
        cJSON_AddItemToArray(images, image);

        // 9729 linear, 9987 linear mipmap linear; 10497 repeat, 33071 clamp to edge.
        int    wrap    = m->texture_repeat ? 10497 : 33071;
        cJSON* sampler = cJSON_CreateObject();
        cJSON_AddNumberToObject(sampler, "magFilter", 9729);
        cJSON_AddNumberToObject(sampler, "minFilter", 9987);
        cJSON_AddNumberToObject(sampler, "wrapS", wrap);
        cJSON_AddNumberToObject(sampler, "wrapT", wrap);
        cJSON_AddItemToArray(samplers, sampler);

        cJSON* texture = cJSON_CreateObject();
        cJSON_AddNumberToObject(texture, "source", cJSON_GetArraySize(images) - 1);
        cJSON_AddNumberToObject(texture, "sampler", cJSON_GetArraySize(samplers) - 1);
        cJSON_AddItemToArray(textures, texture);

        cJSON* ref = cJSON_AddObjectToObject(pbr, "baseColorTexture");
        cJSON_AddNumberToObject(ref, "index", cJSON_GetArraySize(textures) - 1);
    }

    if (m->texture && m->alpha_mask)
    {
        cJSON_AddStringToObject(json, "alphaMode", "MASK");
        cJSON_AddNumberToObject(json, "alphaCutoff", 0.5);
    }
    else if (m->base_color[3] < 0.999f)
        cJSON_AddStringToObject(json, "alphaMode", "BLEND");
    if (m->double_sided)
        cJSON_AddBoolToObject(json, "doubleSided", true);
    return json;
}

b8
geo_write_gltf(const char* path, const geo_part* parts, uint32 part_count, char* error, size_t error_size)
{
    cJSON* root = cJSON_CreateObject();
    cJSON* asset = cJSON_AddObjectToObject(root, "asset");
    cJSON_AddStringToObject(asset, "version", "2.0");
    cJSON_AddStringToObject(asset, "generator", "Meta_Engine Products");

    cJSON* views      = cJSON_CreateArray();
    cJSON* accessors  = cJSON_CreateArray();
    cJSON* materials  = cJSON_CreateArray();
    cJSON* textures   = cJSON_CreateArray();
    cJSON* images     = cJSON_CreateArray();
    cJSON* samplers   = cJSON_CreateArray();
    cJSON* primitives = cJSON_CreateArray();
    byte_buffer buffer = { 0 };

    for (uint32 p = 0; p < part_count; ++p)
    {
        const geo_part* part = &parts[p];
        uint32          n    = part->vertex_count;
        if (!n || !part->index_count)
            continue;

        // Attributes de-interleaved, one view each.
        f32* positions = malloc(n * 3 * sizeof(f32));
        f32* normals   = malloc(n * 3 * sizeof(f32));
        f32* uvs       = malloc(n * 2 * sizeof(f32));
        f32* tangents  = malloc(n * 4 * sizeof(f32));
        f32  lo[3] = { INFINITY, INFINITY, INFINITY }, hi[3] = { -INFINITY, -INFINITY, -INFINITY };
        for (uint32 i = 0; i < n; ++i)
        {
            const geo_vertex* v = &part->vertices[i];
            memcpy(positions + i * 3, v->position, 3 * sizeof(f32));
            memcpy(normals + i * 3, v->normal, 3 * sizeof(f32));
            memcpy(uvs + i * 2, v->uv, 2 * sizeof(f32));
            memcpy(tangents + i * 4, v->tangent, 4 * sizeof(f32));
            for (int a = 0; a < 3; ++a)
            {
                lo[a] = fminf(lo[a], v->position[a]);
                hi[a] = fmaxf(hi[a], v->position[a]);
            }
        }

        cJSON* attributes = cJSON_CreateObject();
        int position = add_accessor(views, accessors, &buffer, positions, n * 3 * sizeof(f32), n, GLTF_FLOAT, "VEC3", GLTF_ARRAY);
        json_add_floats(cJSON_GetArrayItem(accessors, position), "min", lo, 3);   // required for POSITION
        json_add_floats(cJSON_GetArrayItem(accessors, position), "max", hi, 3);
        cJSON_AddNumberToObject(attributes, "POSITION", position);
        cJSON_AddNumberToObject(attributes, "NORMAL",
                                add_accessor(views, accessors, &buffer, normals, n * 3 * sizeof(f32), n, GLTF_FLOAT, "VEC3", GLTF_ARRAY));
        cJSON_AddNumberToObject(attributes, "TEXCOORD_0",
                                add_accessor(views, accessors, &buffer, uvs, n * 2 * sizeof(f32), n, GLTF_FLOAT, "VEC2", GLTF_ARRAY));
        cJSON_AddNumberToObject(attributes, "TANGENT",
                                add_accessor(views, accessors, &buffer, tangents, n * 4 * sizeof(f32), n, GLTF_FLOAT, "VEC4", GLTF_ARRAY));
        free(positions); free(normals); free(uvs); free(tangents);

        cJSON* primitive = cJSON_CreateObject();
        cJSON_AddItemToObject(primitive, "attributes", attributes);
        cJSON_AddNumberToObject(primitive, "indices",
                                add_accessor(views, accessors, &buffer, part->indices, part->index_count * sizeof(uint32),
                                             part->index_count, GLTF_UNSIGNED_INT, "SCALAR", GLTF_ELEMENTS));
        cJSON_AddItemToArray(materials, material_json(&part->material, textures, images, samplers));
        cJSON_AddNumberToObject(primitive, "material", cJSON_GetArraySize(materials) - 1);
        cJSON_AddItemToArray(primitives, primitive);
    }

    char*  encoded = base64_encode_alloc(buffer.data, buffer.size);
    size_t uri_size = strlen(encoded) + 64;
    char*  uri      = malloc(uri_size);
    snprintf(uri, uri_size, "data:application/octet-stream;base64,%s", encoded);
    cJSON* buffers = cJSON_AddArrayToObject(root, "buffers");
    cJSON* buf     = cJSON_CreateObject();
    cJSON_AddNumberToObject(buf, "byteLength", (double)buffer.size);
    cJSON_AddStringToObject(buf, "uri", uri);
    cJSON_AddItemToArray(buffers, buf);
    free(uri);
    free(encoded);
    free(buffer.data);

    cJSON_AddItemToObject(root, "bufferViews", views);
    cJSON_AddItemToObject(root, "accessors", accessors);
    cJSON_AddItemToObject(root, "materials", materials);
    if (cJSON_GetArraySize(images))
    {
        cJSON_AddItemToObject(root, "images", images);
        cJSON_AddItemToObject(root, "samplers", samplers);
        cJSON_AddItemToObject(root, "textures", textures);
    }
    else
    {
        cJSON_Delete(images);
        cJSON_Delete(samplers);
        cJSON_Delete(textures);
    }

    cJSON* meshes = cJSON_AddArrayToObject(root, "meshes");
    cJSON* mesh   = cJSON_CreateObject();
    cJSON_AddItemToObject(mesh, "primitives", primitives);
    cJSON_AddItemToArray(meshes, mesh);
    cJSON* nodes = cJSON_AddArrayToObject(root, "nodes");
    cJSON* node  = cJSON_CreateObject();
    cJSON_AddNumberToObject(node, "mesh", 0);
    cJSON_AddItemToArray(nodes, node);
    cJSON* scenes = cJSON_AddArrayToObject(root, "scenes");
    cJSON* scene  = cJSON_CreateObject();
    cJSON_AddItemToObject(scene, "nodes", cJSON_CreateIntArray((const int[]){ 0 }, 1));
    cJSON_AddItemToArray(scenes, scene);
    cJSON_AddNumberToObject(root, "scene", 0);

    char* text = cJSON_PrintUnformatted(root);
    b8    ok   = text && file_write_string(path, text);
    cJSON_free(text);
    cJSON_Delete(root);
    return ok || set_error(error, error_size, "couldn't write %s", path);
}
