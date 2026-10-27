#pragma once

// Shared plumbing for the model loaders (ModelObj.c, ModelGltf.c). Nothing
// outside Scene/Model*.c should include this.

#include "Model.h"
#include "../Core/Image.h"

char* model_duplicate_string(const char* s);

// Directory part of `path` including the trailing separator ("a/b/c.glb"
// -> "a/b/"), or "" if there is none. Heap-allocated; caller frees.
char* model_directory_of(const char* path);

// Uploads decoded RGBA8 pixels as a mipmapped GPU texture. `srgb` must be
// true for color data (albedo, emissive) and false for data maps
// (normal, roughness, occlusion).
rhi_texture model_upload_image(const image* img, b8 srgb,
                                rhi_texture_filter filter, rhi_texture_wrap wrap);

// Appends to the model's owned arrays. The add_* functions return the new
// element's index (pointers into the arrays are invalidated by later adds).
uint32 model_add_texture(model* m, rhi_texture texture);
uint32 model_add_material(model* m, const material* mat);
uint32 model_add_mesh(model* m, mesh msh);
void   model_add_submesh(model* m, uint32 mesh_index, int32 material_index, const mat4 transform);

// Call once after all meshes/submeshes are added: computes model-space
// bounds and the vertex/triangle totals, and initialises default_material
// if the loader hasn't.
void model_finalize(model* m);
