#include "Timeline.h"

#include "Common/Json.h"
#include "World/Reflect.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Two keys closer than this are at the same time.
#define SAME_TIME 1e-5f


// --- Easing --------------------------------------------------------------------------

static const char* const EASE_NAMES[EASE_COUNT] = { "linear", "in", "out", "in_out", "step", "bezier" };

// The named curves' control points (CSS's ease-in, ease-out, ease-in-out).
static const f32 EASE_IN_CURVE[4]     = { 0.42f, 0.0f, 1.0f, 1.0f };
static const f32 EASE_OUT_CURVE[4]    = { 0.0f, 0.0f, 0.58f, 1.0f };
static const f32 EASE_IN_OUT_CURVE[4] = { 0.42f, 0.0f, 0.58f, 1.0f };

const char*
timeline_ease_name(timeline_ease ease)
{
    return (uint32)ease < EASE_COUNT ? EASE_NAMES[ease] : NULL;
}

b8
timeline_ease_from_name(const char* name, timeline_ease* out_ease)
{
    for (uint32 i = 0; name && i < EASE_COUNT; ++i)
    {
        if (strcmp(name, EASE_NAMES[i]) == 0)
        {
            *out_ease = (timeline_ease)i;
            return true;
        }
    }
    return false;
}

// One coordinate of a cubic bezier from (0, 0) to (1, 1) with inner control
// points a and b, at parameter s.
static f32
bezier_coordinate(f32 a, f32 b, f32 s)
{
    f32 r = 1.0f - s;
    return 3.0f * r * r * s * a + 3.0f * r * s * s * b + s * s * s;
}

// CSS cubic-bezier: find the s where x(s) = u (x is monotonic for x1, x2 in
// [0, 1]), then return y(s).
static f32
bezier_ease(const f32 c[4], f32 u)
{
    f32 lo = 0.0f, hi = 1.0f, s = u;
    for (int i = 0; i < 32; ++i)
    {
        s = 0.5f * (lo + hi);
        if (bezier_coordinate(c[0], c[2], s) < u)
            lo = s;
        else
            hi = s;
    }
    return bezier_coordinate(c[1], c[3], s);
}

f32
timeline_ease_apply(timeline_ease ease, const f32 bezier[4], f32 u)
{
    if (u <= 0.0f) return 0.0f;
    if (u >= 1.0f) return 1.0f;

    switch (ease)
    {
        case EASE_IN:     return bezier_ease(EASE_IN_CURVE, u);
        case EASE_OUT:    return bezier_ease(EASE_OUT_CURVE, u);
        case EASE_IN_OUT: return bezier_ease(EASE_IN_OUT_CURVE, u);
        case EASE_STEP:   return 0.0f;
        case EASE_BEZIER: return bezier_ease(bezier, u);
        default:          return u;
    }
}

// --- Tracks -------------------------------------------------------------------------

void
timeline_init(timeline* tl)
{
    memset(tl, 0, sizeof(*tl));
}

void
timeline_clear(timeline* tl)
{
    for (uint32 i = 0; i < tl->track_count; ++i)
        free(tl->tracks[i].keys);
    tl->track_count = 0;
    tl->time        = 0.0f;
    tl->playing     = false;
}

void
timeline_destroy(timeline* tl)
{
    timeline_clear(tl);
    free(tl->tracks);
    memset(tl, 0, sizeof(*tl));
}

f32
timeline_duration(const timeline* tl)
{
    f32 duration = 0.0f;
    for (uint32 i = 0; i < tl->track_count; ++i)
    {
        const timeline_track* track = &tl->tracks[i];
        if (track->key_count)
            duration = fmaxf(duration, track->keys[track->key_count - 1].time);
    }
    return duration;
}

// The field's floats per value: 1 for a number, 3 for a vec3 or colour, 0
// if it can't be animated.
static uint32
field_width(const field_desc* f)
{
    if (f->via_setter)
        return 0;
    return f->type == FIELD_F32 ? 1 : (f->type == FIELD_VEC3 || f->type == FIELD_COLOR3) ? 3 : 0;
}

// Whether the field limits its values -- the engine's own test (min == max
// means unbounded).
static b8
has_range(const field_desc* f)
{
    return f->min < f->max;
}

// What a track animates: a World component's field, or the custom target's.
typedef struct target_info
{
    uint32            width;
    f32               min, max;   // min == max: unbounded
    b8                nonzero;    // a direction: (0, 0, 0) isn't allowed
    const field_desc* field;      // NULL for the custom target
} target_info;

static b8
is_custom(const timeline* tl, const char* component)
{
    return tl->custom.component && component && strcmp(component, tl->custom.component) == 0;
}

// `component`.`field` if it can be animated; NULL (error filled) otherwise.
static const field_desc*
animatable_field(const timeline* tl, const char* component, const char* field, char* error, size_t error_size)
{
    const component_desc* desc = component ? reflect_component_by_name(component) : NULL;
    if (!desc)
    {
        char names[256] = "";
        for (uint32 t = 0; t < COMPONENT_TYPE_COUNT; ++t)
        {
            const component_desc* d = reflect_component((component_type)t);
            size_t used = strlen(names);
            if (d)
                snprintf(names + used, sizeof(names) - used, "%s%s", used ? ", " : "", d->name);
        }
        if (tl->custom.component)
            snprintf(names + strlen(names), sizeof(names) - strlen(names), ", %s", tl->custom.component);
        set_error(error, error_size, "unknown component \"%s\"; components are: %s", component ? component : "", names);
        return NULL;
    }

    const field_desc* f = field ? reflect_field(desc, field) : NULL;
    if (f && field_width(f))
        return f;

    char names[512] = "";
    for (uint32 i = 0; i < desc->field_count; ++i)
    {
        size_t used = strlen(names);
        if (field_width(&desc->fields[i]))
            snprintf(names + used, sizeof(names) - used, "%s%s", used ? ", " : "", desc->fields[i].name);
    }
    if (f)
        set_error(error, error_size, "%s.%s can't be animated (only numbers, vec3s and colours); %s's animatable fields are: %s",
                  desc->name, field, desc->name, *names ? names : "(none)");
    else
        set_error(error, error_size, "%s has no field \"%s\"; its animatable fields are: %s",
                  desc->name, field ? field : "", *names ? names : "(none)");
    return NULL;
}

// The target's width, range and rules; false (error filled) if it can't be animated.
static b8
describe_target(const timeline* tl, const char* component, const char* field, target_info* out,
                char* error, size_t error_size)
{
    memset(out, 0, sizeof(*out));
    if (is_custom(tl, component))
    {
        if (!tl->custom.describe(tl->custom.user, field, &out->width, &out->min, &out->max, error, error_size))
            return false;
        if (out->width < 1 || out->width > TIMELINE_VALUE_MAX)
            return set_error(error, error_size, "%s.%s has %u floats; at most %d can be animated", component, field,
                             out->width, TIMELINE_VALUE_MAX);
        return true;
    }

    const field_desc* f = animatable_field(tl, component, field, error, error_size);
    if (!f)
        return false;
    out->width   = field_width(f);
    out->min     = has_range(f) ? f->min : 0.0f;
    out->max     = has_range(f) ? f->max : 0.0f;
    out->nonzero = f->nonzero;
    out->field   = f;
    return true;
}

uint32
timeline_field_width(const timeline* tl, const char* component, const char* field, char* error, size_t error_size)
{
    target_info info;
    return describe_target(tl, component, field, &info, error, error_size) ? info.width : 0;
}

timeline_track*
timeline_find_track(timeline* tl, const char* entity, const char* component, const char* field)
{
    for (uint32 i = 0; i < tl->track_count; ++i)
    {
        timeline_track* track = &tl->tracks[i];
        if (strcmp(track->entity, entity) == 0 && strcmp(track->component, component) == 0
            && strcmp(track->field, field) == 0)
            return track;
    }
    return NULL;
}

// What the track animates, after checking the names fit and it can be
// animated; false (error filled) otherwise.
static b8
check_target(const timeline* tl, const char* entity, const char* component, const char* field, target_info* out,
             char* error, size_t error_size)
{
    if (!entity || !entity[0] || strlen(entity) >= ENTITY_NAME_MAX)
        return set_error(error, error_size, "\"entity\" must be a name of 1 to %d characters", ENTITY_NAME_MAX - 1);
    if (!component || strlen(component) >= TIMELINE_COMPONENT_MAX || !field || strlen(field) >= TIMELINE_FIELD_MAX)
        return set_error(error, error_size, "\"component\" and \"field\" must be given");
    return describe_target(tl, component, field, out, error, error_size);
}

static timeline_track*
find_or_add_track(timeline* tl, const char* entity, const char* component, const char* field, uint32 width)
{
    timeline_track* track = timeline_find_track(tl, entity, component, field);
    if (track)
        return track;

    if (tl->track_count == tl->track_capacity)
    {
        tl->track_capacity = tl->track_capacity ? tl->track_capacity * 2 : 8;
        tl->tracks         = realloc(tl->tracks, tl->track_capacity * sizeof(*tl->tracks));
    }
    track = &tl->tracks[tl->track_count++];
    memset(track, 0, sizeof(*track));
    snprintf(track->entity, sizeof(track->entity), "%s", entity);
    snprintf(track->component, sizeof(track->component), "%s", component);
    snprintf(track->field, sizeof(track->field), "%s", field);
    track->width = width;
    return track;
}

static void
reserve_keys(timeline_track* track, uint32 count)
{
    if (count <= track->key_capacity)
        return;
    track->key_capacity = count < 8 ? 8 : count;
    track->keys         = realloc(track->keys, track->key_capacity * sizeof(*track->keys));
}

static int
compare_key_times(const void* a, const void* b)
{
    f32 ta = ((const timeline_key*)a)->time, tb = ((const timeline_key*)b)->time;
    return (ta > tb) - (ta < tb);
}

// A key's time and ease, and its value against the field's rules -- the
// same ones component.set applies: within the field's range, and not zero
// for a direction.
static b8
check_key(const timeline_key* key, const target_info* target, const char* field, char* error, size_t error_size)
{
    if (!isfinite(key->time) || key->time < 0.0f)
        return set_error(error, error_size, "a key's time must be 0 or more seconds (got %g)", key->time);
    if ((uint32)key->ease >= EASE_COUNT)
        return set_error(error, error_size, "unknown ease");
    if (key->ease == EASE_BEZIER && (key->bezier[0] < 0.0f || key->bezier[0] > 1.0f || key->bezier[2] < 0.0f || key->bezier[2] > 1.0f))
        return set_error(error, error_size, "a bezier's x1 and x2 must be in [0, 1] (got %g and %g)", key->bezier[0], key->bezier[2]);

    for (uint32 i = 0; target->min < target->max && i < target->width; ++i)
    {
        if (key->value[i] < target->min || key->value[i] > target->max)
            return set_error(error, error_size, "the key at %g s: %s must be from %g to %g (got %g)",
                             key->time, field, target->min, target->max, key->value[i]);
    }
    if (target->nonzero && fabsf(key->value[0]) + fabsf(key->value[1]) + fabsf(key->value[2]) < 1e-6f)
        return set_error(error, error_size, "the key at %g s: %s is a direction and can't be (0, 0, 0)", key->time, field);
    return true;
}

b8
timeline_set_track(timeline* tl, const char* entity, const char* component, const char* field,
                   const timeline_key* keys, uint32 key_count, char* error, size_t error_size)
{
    target_info target;
    if (!check_target(tl, entity, component, field, &target, error, error_size))
        return false;
    if (key_count == 0)
        return set_error(error, error_size, "a track needs at least one key");

    timeline_key* sorted = malloc(key_count * sizeof(*sorted));
    memcpy(sorted, keys, key_count * sizeof(*sorted));
    qsort(sorted, key_count, sizeof(*sorted), compare_key_times);

    for (uint32 i = 0; i < key_count; ++i)
    {
        b8 ok = check_key(&sorted[i], &target, field, error, error_size);
        if (ok && i > 0 && sorted[i].time - sorted[i - 1].time < SAME_TIME)
            ok = set_error(error, error_size, "two keys are at %g s: a track has one key per time", sorted[i].time);
        if (!ok)
        {
            free(sorted);
            return false;
        }
    }

    timeline_track* track = find_or_add_track(tl, entity, component, field, target.width);
    free(track->keys);
    track->keys         = sorted;
    track->key_count    = key_count;
    track->key_capacity = key_count;
    return true;
}

b8
timeline_add_key(timeline* tl, const char* entity, const char* component, const char* field,
                 const timeline_key* key, char* error, size_t error_size)
{
    target_info target;
    if (!check_target(tl, entity, component, field, &target, error, error_size)
        || !check_key(key, &target, field, error, error_size))
        return false;

    timeline_track* track = find_or_add_track(tl, entity, component, field, target.width);

    uint32 at = 0;
    while (at < track->key_count && track->keys[at].time < key->time - SAME_TIME)
        ++at;
    if (at < track->key_count && fabsf(track->keys[at].time - key->time) < SAME_TIME)
    {
        track->keys[at] = *key;   // replaces the key at that time
        return true;
    }

    reserve_keys(track, track->key_count + 1);
    memmove(&track->keys[at + 1], &track->keys[at], (track->key_count - at) * sizeof(*track->keys));
    track->keys[at] = *key;
    track->key_count++;
    return true;
}

uint32
timeline_remove_tracks(timeline* tl, const char* entity, const char* component, const char* field)
{
    uint32 kept = 0, removed = 0;
    for (uint32 i = 0; i < tl->track_count; ++i)
    {
        timeline_track* track = &tl->tracks[i];
        b8 match = strcmp(track->entity, entity) == 0
                   && (!component || strcmp(track->component, component) == 0)
                   && (!field || strcmp(track->field, field) == 0);
        if (match)
        {
            free(track->keys);
            ++removed;
        }
        else
            tl->tracks[kept++] = *track;
    }
    tl->track_count = kept;
    return removed;
}

uint32
timeline_remove_keys(timeline* tl, const char* entity, const char* component, const char* field, f32 from, f32 to)
{
    timeline_track* track = timeline_find_track(tl, entity, component, field);
    if (!track)
        return 0;

    uint32 kept = 0;
    for (uint32 i = 0; i < track->key_count; ++i)
    {
        f32 t = track->keys[i].time;
        if (t < from - SAME_TIME || t >= to - SAME_TIME)
            track->keys[kept++] = track->keys[i];
    }
    uint32 removed   = track->key_count - kept;
    track->key_count = kept;
    if (kept == 0)
        timeline_remove_tracks(tl, entity, component, field);
    return removed;
}

// --- Evaluation -----------------------------------------------------------------------

void
timeline_sample(const timeline_track* track, f32 t, f32 out[TIMELINE_VALUE_MAX])
{
    memset(out, 0, TIMELINE_VALUE_MAX * sizeof(f32));
    if (!track->key_count)
        return;

    const timeline_key* keys = track->keys;
    uint32              last = track->key_count - 1;
    if (t <= keys[0].time || last == 0)
    {
        memcpy(out, keys[0].value, track->width * sizeof(f32));
        return;
    }
    if (t >= keys[last].time)
    {
        memcpy(out, keys[last].value, track->width * sizeof(f32));
        return;
    }

    // The segment [a, b] holding t: the last key at or before it.
    uint32 lo = 0, hi = last;
    while (hi - lo > 1)
    {
        uint32 mid = (lo + hi) / 2;
        if (keys[mid].time <= t)
            lo = mid;
        else
            hi = mid;
    }
    const timeline_key* a = &keys[lo];
    const timeline_key* b = &keys[lo + 1];

    f32 e = timeline_ease_apply(a->ease, a->bezier, (t - a->time) / (b->time - a->time));
    for (uint32 i = 0; i < track->width; ++i)
        out[i] = a->value[i] + (b->value[i] - a->value[i]) * e;
}

// Writes `value` into the entity's field (or the custom target's item, which
// keeps its own values in range). False if the entity or component is missing.
static b8
write_field(const timeline* tl, world* w, const timeline_track* track, const f32* value)
{
    if (is_custom(tl, track->component))
        return tl->custom.write(tl->custom.user, track->entity, track->field, value, track->width);

    entity_id e = world_find(w, track->entity);
    const component_desc* desc = reflect_component_by_name(track->component);
    const field_desc*     f    = desc ? reflect_field(desc, track->field) : NULL;
    void* data = e && f ? reflect_component_data(w, e, desc->type) : NULL;
    if (!data)
        return false;

    // Keys are within range, but a bezier ease can overshoot between them.
    f32 v[TIMELINE_VALUE_MAX];
    memcpy(v, value, sizeof(v));
    if (has_range(f))
    {
        for (uint32 i = 0; i < track->width; ++i)
            v[i] = glm_clamp(v[i], f->min, f->max);
    }
    // A direction passing through zero keeps the last one it had.
    if (f->nonzero && fabsf(v[0]) + fabsf(v[1]) + fabsf(v[2]) < 1e-6f)
        return true;

    memcpy((uint8*)data + f->offset, v, track->width * sizeof(f32));

    // A material override field only applies with its bit set.
    if (f->override_bit && desc->type == COMPONENT_MESH_RENDERER)
        ((c_mesh_renderer*)data)->material.fields |= f->override_bit;
    return true;
}

uint32
timeline_evaluate(timeline* tl, world* w, f32 t, uint32* out_skipped)
{
    uint32 written = 0, skipped = 0;
    tl->time = t;
    for (uint32 i = 0; i < tl->track_count; ++i)
    {
        f32 value[TIMELINE_VALUE_MAX];
        timeline_sample(&tl->tracks[i], t, value);
        if (write_field(tl, w, &tl->tracks[i], value))
            ++written;
        else
            ++skipped;
    }
    if (out_skipped)
        *out_skipped = skipped;
    return written;
}

// --- JSON ------------------------------------------------------------------------------

cJSON*
timeline_track_to_json(const timeline_track* track)
{
    cJSON* json = cJSON_CreateObject();
    cJSON_AddStringToObject(json, "entity", track->entity);
    cJSON_AddStringToObject(json, "component", track->component);
    cJSON_AddStringToObject(json, "field", track->field);

    cJSON* keys = cJSON_AddArrayToObject(json, "keys");
    for (uint32 k = 0; k < track->key_count; ++k)
    {
        const timeline_key* key = &track->keys[k];
        cJSON* item = cJSON_CreateObject();
        cJSON_AddNumberToObject(item, "t", json_round6(key->time));
        if (track->width == 1)
            cJSON_AddNumberToObject(item, "value", json_round6(key->value[0]));
        else
            json_add_floats(item, "value", key->value, (int)track->width);
        if (key->ease != EASE_LINEAR)
            cJSON_AddStringToObject(item, "ease", timeline_ease_name(key->ease));
        if (key->ease == EASE_BEZIER)
            json_add_floats(item, "bezier", key->bezier, 4);
        cJSON_AddItemToArray(keys, item);
    }
    return json;
}

cJSON*
timeline_to_json(const timeline* tl)
{
    cJSON* json = cJSON_CreateObject();
    cJSON_AddNumberToObject(json, "duration", json_round6(timeline_duration(tl)));
    cJSON* tracks = cJSON_AddArrayToObject(json, "tracks");
    for (uint32 i = 0; i < tl->track_count; ++i)
        cJSON_AddItemToArray(tracks, timeline_track_to_json(&tl->tracks[i]));
    return json;
}

b8
timeline_key_from_json(const cJSON* json, uint32 width, timeline_key* out, char* error, size_t error_size)
{
    memset(out, 0, sizeof(*out));
    if (!cJSON_IsObject(json))
        return set_error(error, error_size, "a key must be an object like {\"t\": 0, \"value\": ...}");

    const cJSON* item;
    cJSON_ArrayForEach(item, json)
    {
        if (strcmp(item->string, "t") && strcmp(item->string, "value") && strcmp(item->string, "ease")
            && strcmp(item->string, "bezier"))
            return set_error(error, error_size, "a key doesn't take \"%s\"; it takes t, value, ease, bezier", item->string);
    }

    const cJSON* t = cJSON_GetObjectItemCaseSensitive(json, "t");
    if (!cJSON_IsNumber(t))
        return set_error(error, error_size, "a key needs \"t\": its time in seconds");
    out->time = (f32)t->valuedouble;

    const cJSON* value = cJSON_GetObjectItemCaseSensitive(json, "value");
    b8 value_ok = width == 1 ? cJSON_IsNumber(value) && isfinite(value->valuedouble)
                             : json_read_floats(value, out->value, (int)width);
    if (!value_ok)
        return width == 1 ? set_error(error, error_size, "this field's key \"value\" must be a number")
                          : set_error(error, error_size, "this field's key \"value\" must be an array of %u numbers", width);
    if (width == 1)
        out->value[0] = (f32)value->valuedouble;

    const cJSON* ease = cJSON_GetObjectItemCaseSensitive(json, "ease");
    if (ease && (!cJSON_IsString(ease) || !timeline_ease_from_name(ease->valuestring, &out->ease)))
        return set_error(error, error_size, "\"ease\" must be \"linear\", \"in\", \"out\", \"in_out\", \"step\" or \"bezier\"");

    const cJSON* bezier = cJSON_GetObjectItemCaseSensitive(json, "bezier");
    if (out->ease == EASE_BEZIER && !json_read_floats(bezier, out->bezier, 4))
        return set_error(error, error_size, "\"ease\": \"bezier\" needs \"bezier\": [x1, y1, x2, y2] (CSS cubic-bezier)");
    if (out->ease != EASE_BEZIER && bezier)
        return set_error(error, error_size, "\"bezier\" only goes with \"ease\": \"bezier\"");

    // Times, ranges and the bezier's x values are checked when the key goes
    // into a track (timeline_set_track(), timeline_add_key()).
    return true;
}

b8
timeline_set_track_json(timeline* tl, const char* entity, const char* component, const char* field,
                        const cJSON* keys, char* error, size_t error_size)
{
    target_info target;
    if (!check_target(tl, entity, component, field, &target, error, error_size))
        return false;
    if (!cJSON_IsArray(keys) || cJSON_GetArraySize(keys) == 0)
        return set_error(error, error_size, "\"keys\" must be a non-empty array of {\"t\": seconds, \"value\": ..., \"ease\": ...}");

    uint32        count  = (uint32)cJSON_GetArraySize(keys);
    timeline_key* parsed = calloc(count, sizeof(*parsed));
    uint32        i      = 0;
    const cJSON*  key;
    b8            ok = true;
    cJSON_ArrayForEach(key, keys)
    {
        char key_error[256];
        if (!timeline_key_from_json(key, target.width, &parsed[i], key_error, sizeof(key_error)))
        {
            ok = set_error(error, error_size, "keys[%u]: %s", i, key_error);
            break;
        }
        ++i;
    }
    if (ok)
        ok = timeline_set_track(tl, entity, component, field, parsed, count, error, error_size);
    free(parsed);
    return ok;
}

// One track from JSON into `tl`.
static b8
track_from_json(timeline* tl, const cJSON* json, char* error, size_t error_size)
{
    const cJSON* entity    = cJSON_GetObjectItemCaseSensitive(json, "entity");
    const cJSON* component = cJSON_GetObjectItemCaseSensitive(json, "component");
    const cJSON* field     = cJSON_GetObjectItemCaseSensitive(json, "field");
    const cJSON* keys      = cJSON_GetObjectItemCaseSensitive(json, "keys");
    if (!cJSON_IsString(entity) || !cJSON_IsString(component) || !cJSON_IsString(field))
        return set_error(error, error_size, "a track needs \"entity\", \"component\" and \"field\" (strings) and \"keys\"");
    return timeline_set_track_json(tl, entity->valuestring, component->valuestring, field->valuestring, keys,
                                   error, error_size);
}

b8
timeline_from_json(timeline* tl, const cJSON* json, char* error, size_t error_size)
{
    const cJSON* tracks = cJSON_GetObjectItemCaseSensitive(json, "tracks");
    if (!cJSON_IsArray(tracks))
        return set_error(error, error_size, "a timeline needs \"tracks\": an array");

    timeline loaded;
    timeline_init(&loaded);
    loaded.custom = tl->custom;   // its tracks are checked against the same targets
    const cJSON* track;
    cJSON_ArrayForEach(track, tracks)
    {
        if (!track_from_json(&loaded, track, error, error_size))
        {
            timeline_destroy(&loaded);
            return false;
        }
    }

    timeline_destroy(tl);
    *tl = loaded;
    return true;
}
