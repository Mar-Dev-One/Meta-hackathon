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
