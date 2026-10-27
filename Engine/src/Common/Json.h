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
