#include "Json.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>

b8
set_error(char* error, size_t error_size, const char* format, ...)
{
    if (error && error_size)
    {
        va_list args;
        va_start(args, format);
        vsnprintf(error, error_size, format, args);
        va_end(args);
    }
    return false;
}

f64
json_round6(f32 value)
{
    return round((f64)value * 1e6) / 1e6;
}

void
json_add_floats(cJSON* object, const char* name, const f32* values, int count)
{
    cJSON* array = cJSON_AddArrayToObject(object, name);
    for (int i = 0; i < count; ++i)
        cJSON_AddItemToArray(array, cJSON_CreateNumber(json_round6(values[i])));
}

b8
json_read_floats(const cJSON* json, f32* out, int count)
{
    if (!cJSON_IsArray(json) || cJSON_GetArraySize(json) != count)
        return false;
    for (int i = 0; i < count; ++i)
    {
        const cJSON* v = cJSON_GetArrayItem(json, i);
        if (!cJSON_IsNumber(v) || !isfinite(v->valuedouble))
            return false;
        out[i] = (f32)v->valuedouble;
    }
    return true;
}

int
arg_number(const cJSON* args, const char* name, f32 min, f32 max, f32* out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble) || item->valuedouble < min || item->valuedouble > max)
        return set_error(error, error_size, "\"%s\" must be a number from %g to %g", name, min, max), -1;
    *out = (f32)item->valuedouble;
    return 1;
}

int
arg_vec3(const cJSON* args, const char* name, f32 out[3], char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!json_read_floats(item, out, 3))
        return set_error(error, error_size, "\"%s\" must be an array of three numbers, e.g. [0, 1.5, 3]", name), -1;
    return 1;
}

int
arg_bool(const cJSON* args, const char* name, b8* out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!cJSON_IsBool(item))
        return set_error(error, error_size, "\"%s\" must be true or false", name), -1;
    *out = cJSON_IsTrue(item);
    return 1;
}

int
arg_string(const cJSON* args, const char* name, const char** out, char* error, size_t error_size)
{
    const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, name);
    if (!item)
        return 0;
    if (!cJSON_IsString(item) || !item->valuestring[0])
        return set_error(error, error_size, "\"%s\" must be a non-empty string", name), -1;
    *out = item->valuestring;
    return 1;
}
