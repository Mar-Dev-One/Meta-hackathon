// The timeline's host commands (Studio.h lists them). They run on the
// studio's timeline and world; every edit re-evaluates the timeline at its
// current time, so the scene always shows what the timeline says.

#include "TimelineCommands.h"

#include "Studio/Studio.h"
#include "Timeline/Timeline.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

// Writes the timeline into the world at its current time.
static void
refresh(studio* s)
{
    timeline_evaluate(&s->timeline, s->w, s->timeline.time, NULL);
    world_update(s->w);
}

static b8
read_target(const cJSON* args, const char** entity, const char** component, const char** field,
            b8 component_required, char* error, size_t error_size)
{
    const cJSON* e = cJSON_GetObjectItemCaseSensitive(args, "entity");
    const cJSON* c = cJSON_GetObjectItemCaseSensitive(args, "component");
    const cJSON* f = cJSON_GetObjectItemCaseSensitive(args, "field");
    if (!cJSON_IsString(e) || (c && !cJSON_IsString(c)) || (f && !cJSON_IsString(f)))
    {
        snprintf(error, error_size, "\"entity\", \"component\" and \"field\" must be strings");
        return false;
    }
    if (component_required && (!c || !f))
    {
        snprintf(error, error_size, "give \"entity\", \"component\" and \"field\", e.g. \"camera\", \"Transform\", \"position\"");
        return false;
    }
    *entity    = e->valuestring;
    *component = c ? c->valuestring : NULL;
    *field     = f ? f->valuestring : NULL;
    return true;
}

static cJSON*
describe_track(studio* s, timeline_track* track)
{
    cJSON* result = timeline_track_to_json(track);
    cJSON_AddBoolToObject(result, "entity_exists", world_find(s->w, track->entity) != ENTITY_NULL);
    cJSON_AddNumberToObject(result, "duration", timeline_duration(&s->timeline));
    return result;
}

static b8
cmd_set_track(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s = (studio*)user;
    const char *entity, *component, *field;
    if (!read_target(args, &entity, &component, &field, true, error, error_size))
        return false;

    uint32 width = timeline_field_width(component, field, error, error_size);
    if (!width)
        return false;

    const cJSON* keys = cJSON_GetObjectItemCaseSensitive(args, "keys");
    if (!cJSON_IsArray(keys) || cJSON_GetArraySize(keys) == 0)
    {
        snprintf(error, error_size, "\"keys\" must be a non-empty array of {\"t\": seconds, \"value\": ..., \"ease\": ...}");
        return false;
    }

    uint32        count  = (uint32)cJSON_GetArraySize(keys);
    timeline_key* parsed = calloc(count, sizeof(*parsed));
    uint32        i      = 0;
    const cJSON*  key;
    b8            ok = true;
    cJSON_ArrayForEach(key, keys)
    {
        char key_error[256];
        if (!timeline_key_from_json(key, width, &parsed[i], key_error, sizeof(key_error)))
        {
            snprintf(error, error_size, "keys[%u]: %s", i, key_error);
            ok = false;
            break;
        }
        ++i;
    }
    if (ok)
        ok = timeline_set_track(&s->timeline, entity, component, field, parsed, count, error, error_size);
    free(parsed);
    if (!ok)
        return false;

    refresh(s);
    *out_result = describe_track(s, timeline_find_track(&s->timeline, entity, component, field));
    return true;
}

static b8
cmd_add_key(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s = (studio*)user;
    const char *entity, *component, *field;
    if (!read_target(args, &entity, &component, &field, true, error, error_size))
        return false;

    uint32 width = timeline_field_width(component, field, error, error_size);
    if (!width)
        return false;

    // The key's own fields sit next to the target's in args.
    cJSON* key_json = cJSON_CreateObject();
    const char* const KEY_FIELDS[] = { "t", "value", "ease", "bezier" };
    for (int i = 0; i < 4; ++i)
    {
        const cJSON* item = cJSON_GetObjectItemCaseSensitive(args, KEY_FIELDS[i]);
        if (item)
            cJSON_AddItemToObject(key_json, KEY_FIELDS[i], cJSON_Duplicate(item, true));
    }
    timeline_key key;
    b8 ok = timeline_key_from_json(key_json, width, &key, error, error_size)
            && timeline_add_key(&s->timeline, entity, component, field, &key, error, error_size);
    cJSON_Delete(key_json);
    if (!ok)
        return false;

    refresh(s);
    *out_result = describe_track(s, timeline_find_track(&s->timeline, entity, component, field));
    return true;
}

static b8
cmd_remove_track(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s = (studio*)user;
    const char *entity, *component, *field;
    if (!read_target(args, &entity, &component, &field, false, error, error_size))
        return false;

    uint32 removed = timeline_remove_tracks(&s->timeline, entity, component, field);
    *out_result = cJSON_CreateObject();
    cJSON_AddNumberToObject(*out_result, "removed", removed);
    return true;
}

static b8
cmd_clear(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)out_result; (void)error; (void)error_size;
    timeline_clear(&((studio*)user)->timeline);
    return true;
}

static cJSON*
describe_timeline(const studio* s)
{
    cJSON* result = timeline_to_json(&s->timeline);
    cJSON_AddNumberToObject(result, "time", round(s->timeline.time * 1e6) / 1e6);
    cJSON_AddBoolToObject(result, "playing", s->timeline.playing);
    cJSON_AddBoolToObject(result, "loop", s->timeline.loop);
    return result;
}

static b8
cmd_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    *out_result = describe_timeline((studio*)user);
    return true;
}

static b8
cmd_seek(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*      s = (studio*)user;
    const cJSON* t = cJSON_GetObjectItemCaseSensitive(args, "t");
    if (!cJSON_IsNumber(t) || !isfinite(t->valuedouble) || t->valuedouble < 0.0)
    {
        snprintf(error, error_size, "\"t\" must be a time of 0 or more seconds");
        return false;
    }

    uint32 skipped = 0;
    s->timeline.playing = false;
    uint32 written      = timeline_evaluate(&s->timeline, s->w, (f32)t->valuedouble, &skipped);
    world_update(s->w);

    *out_result = cJSON_CreateObject();
    cJSON_AddNumberToObject(*out_result, "time", t->valuedouble);
    cJSON_AddNumberToObject(*out_result, "tracks_written", written);
    cJSON_AddNumberToObject(*out_result, "tracks_skipped", skipped);
    return true;
}

static b8
cmd_play(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*      s    = (studio*)user;
    const cJSON* from = cJSON_GetObjectItemCaseSensitive(args, "from");
    const cJSON* loop = cJSON_GetObjectItemCaseSensitive(args, "loop");
    if ((from && (!cJSON_IsNumber(from) || from->valuedouble < 0.0)) || (loop && !cJSON_IsBool(loop)))
    {
        snprintf(error, error_size, "\"from\" must be 0 or more seconds and \"loop\" true or false");
        return false;
    }

    if (from)
        s->timeline.time = (f32)from->valuedouble;
    else if (s->timeline.time >= timeline_duration(&s->timeline))
        s->timeline.time = 0.0f;   // played to the end: start over
    if (loop)
        s->timeline.loop = cJSON_IsTrue(loop);
    s->timeline.playing = true;
    *out_result = describe_timeline(s);
    return true;
}

static b8
cmd_pause(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    studio* s = (studio*)user;
    s->timeline.playing = false;
    *out_result = describe_timeline(s);
    return true;
}

// --- Table ----------------------------------------------------------------------------

// The field a track animates: the first three arguments of set_track and add_key.
#define TARGET_ARGS                                                                                           \
    { "entity", "string", true, "the entity's name, e.g. \"camera\"" },                                       \
    { "component", "string", true, "\"Transform\", \"Camera\", \"Light\", \"MeshRenderer\", ..." },           \
    { "field", "string", true, "e.g. \"position\", \"rotation_deg\", \"fov_degrees\", \"intensity\", \"material.roughness\"" }

static const cmd_arg SET_TRACK_ARGS[] = {
    TARGET_ARGS,
    { "keys", "array", true, "[{\"t\": seconds, \"value\": number or [x, y, z], \"ease\": \"linear\" | \"in\" | \"out\" | "
                             "\"in_out\" | \"step\" | \"bezier\", \"bezier\": [x1, y1, x2, y2]}]; ease is towards the next key" },
};

static const cmd_arg ADD_KEY_ARGS[] = {
    TARGET_ARGS,
    { "t", "number", true, "seconds" },
    { "value", "array", true, "a number, or [x, y, z] for vec3 and colour fields" },
    { "ease", "string", false, "towards the next key: linear (default), in, out, in_out, step, bezier" },
    { "bezier", "array", false, "[x1, y1, x2, y2] for ease \"bezier\" (CSS cubic-bezier)" },
};

static const cmd_arg REMOVE_ARGS[] = {
    { "entity", "string", true, "the entity's name" },
    { "component", "string", false, "only this component's tracks" },
    { "field", "string", false, "only this field's track" },
};

static const cmd_arg SEEK_ARGS[] = {
    { "t", "number", true, "seconds" },
};

static const cmd_arg PLAY_ARGS[] = {
    { "from", "number", false, "seconds (default: where it is, or 0 at the end)" },
    { "loop", "boolean", false, "start over after the last key" },
};

#define COUNT_OF(a) (uint32)(sizeof(a) / sizeof((a)[0]))

static const cmd_host_command TIMELINE_COMMANDS[] = {
    { "timeline.set_track", "Animates one field of one entity: replaces its track with these keys and shows the result at the current time.",
      SET_TRACK_ARGS, COUNT_OF(SET_TRACK_ARGS), false, cmd_set_track },
    { "timeline.add_key", "Adds a key to a field's track (creating it), replacing any key at the same time.",
      ADD_KEY_ARGS, COUNT_OF(ADD_KEY_ARGS), false, cmd_add_key },
    { "timeline.remove_track", "Removes an entity's tracks: all of them, a component's, or one field's.",
      REMOVE_ARGS, COUNT_OF(REMOVE_ARGS), false, cmd_remove_track },
    { "timeline.clear", "Removes every track.",
      NULL, 0, false, cmd_clear },
    { "timeline.get", "Every track and key, the duration (the last key's time), the current time and whether it's playing.",
      NULL, 0, false, cmd_get },
    { "timeline.seek", "Stops playing and shows the scene at time t: every animated field set to its value then.",
      SEEK_ARGS, COUNT_OF(SEEK_ARGS), false, cmd_seek },
    { "timeline.play", "Plays the timeline in real time in the Studio's window (a preview; frames for video are rendered per time).",
      PLAY_ARGS, COUNT_OF(PLAY_ARGS), false, cmd_play },
    { "timeline.pause", "Stops playing where it is.",
      NULL, 0, false, cmd_pause },
};

const cmd_host_command*
timeline_commands(uint32* out_count)
{
    *out_count = COUNT_OF(TIMELINE_COMMANDS);
    return TIMELINE_COMMANDS;
}
