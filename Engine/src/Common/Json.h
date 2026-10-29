#pragma once

#include "Core/Defines.h"

#include "cJSON.h"

#include <stddef.h>

// Small helpers every part of Meta_Engine uses for JSON and error messages.
// (The engine has its own, but they're private to its files.)

// Formats into `error` (may be NULL) and returns false, so a check can
// `return set_error(error, error_size, "...", ...);`.
b8 set_error(char* error, size_t error_size, const char* format, ...);

// `value` rounded to 6 decimals, so JSON shows 0.3 rather than 0.30000001.
f64 json_round6(f32 value);

// Adds `count` floats as a JSON array named `name`, rounded.
void json_add_floats(cJSON* object, const char* name, const f32* values, int count);

// Reads an array of exactly `count` finite numbers. False (out partly
// written) if `json` isn't one.
b8 json_read_floats(const cJSON* json, f32* out, int count);

// "#RRGGBB" or "#RRGGBBAA" into out[0..3] (alpha 1 when absent), each 0..1;
// with `to_linear`, the colour channels are converted from sRGB to linear
// (for lighting and materials; text, drawn after tone mapping, stays sRGB).
// False if `text` isn't one.
b8 parse_hex_color(const char* text, f32 out[4], b8 to_linear);

// Optional command arguments. Each returns 1 if `name` is in `args` and
// valid (written to *out), 0 if it's absent (*out untouched), and -1
// (error filled) if it's invalid.
int arg_number(const cJSON* args, const char* name, f32 min, f32 max, f32* out, char* error, size_t error_size);
int arg_vec3(const cJSON* args, const char* name, f32 out[3], char* error, size_t error_size);
int arg_bool(const cJSON* args, const char* name, b8* out, char* error, size_t error_size);
int arg_string(const cJSON* args, const char* name, const char** out, char* error, size_t error_size);
// A colour: "#RRGGBB" (sRGB, as palettes give colours; made linear) or
// [r, g, b] (linear). Writes out[0..2].
int arg_color(const cJSON* args, const char* name, f32 out[3], char* error, size_t error_size);
