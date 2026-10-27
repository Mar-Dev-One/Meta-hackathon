#pragma once

#include "../RHI_Backend.h"

// Fills out_api with this backend's function pointers. This is the
// only symbol src/RHI/OpenGL exposes outside itself.
void rhi_gl_get_backend(rhi_backend_api* out_api);
