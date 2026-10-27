#pragma once

#include "Core/Defines.h"
#include "World/Components.h"
#include "World/World.h"

#include "cJSON.h"

// Keyframe animation of any numeric field of any component: a camera's
// position and field of view, a light's intensity and colour, a material's
// roughness. A track names an entity, a component and one of its fields
// (World/Reflect.h's names: "Transform" / "position", "Light" / "intensity",
// "MeshRenderer" / "material.base_color") and holds keys in time order.
//
// Tracks name their entity rather than holding its ID, so they survive undo
// and scene loads; an entity that doesn't exist (yet) is skipped.
//
// The timeline is evaluated at an absolute time -- timeline_evaluate(t) --
// never by adding up frame times, so a frame rendered on its own looks the
// same as in the middle of a sequence.
//
// Rotations are Transform's Euler degrees, interpolated per axis as given:
// going from 350 to 10 turns the long way round, so write -10 for the short one.

#define TIMELINE_COMPONENT_MAX 32
#define TIMELINE_FIELD_MAX     64
#define TIMELINE_VALUE_MAX     4

// How a key moves on to the next one. The named curves are CSS's.
typedef enum timeline_ease
{
    EASE_LINEAR,
    EASE_IN,        // cubic-bezier(0.42, 0, 1, 1): starts slow
    EASE_OUT,       // cubic-bezier(0, 0, 0.58, 1): ends slow
    EASE_IN_OUT,    // cubic-bezier(0.42, 0, 0.58, 1): slow at both ends
    EASE_STEP,      // holds this key's value until the next key
    EASE_BEZIER,    // the key's own cubic-bezier(x1, y1, x2, y2)
    EASE_COUNT
} timeline_ease;

// "linear", "in", "out", "in_out", "step", "bezier"; NULL out of range.
const char* timeline_ease_name(timeline_ease ease);
b8          timeline_ease_from_name(const char* name, timeline_ease* out_ease);

// Progress through a segment, u in [0, 1], eased. `bezier` is only read
// for EASE_BEZIER (x1, y1, x2, y2; x1 and x2 in [0, 1]).
f32 timeline_ease_apply(timeline_ease ease, const f32 bezier[4], f32 u);

typedef struct timeline_key
{
    f32           time;                        // seconds
    f32           value[TIMELINE_VALUE_MAX];   // the first `width` are used
    timeline_ease ease;                        // towards the next key
    f32           bezier[4];                   // for EASE_BEZIER
} timeline_key;

typedef struct timeline_track
{
    char entity[ENTITY_NAME_MAX];
    char component[TIMELINE_COMPONENT_MAX];
    char field[TIMELINE_FIELD_MAX];
    uint32 width;                 // floats per value: 1 (a number) or 3 (vec3, colour)

    timeline_key* keys;           // sorted by time, no two at the same time
    uint32        key_count;
    uint32        key_capacity;
} timeline_track;

typedef struct timeline
{
    timeline_track* tracks;
    uint32          track_count;
    uint32          track_capacity;

    f32 time;      // where it was last evaluated
    b8  playing;   // advanced in real time by the app (a preview)
    b8  loop;      // while playing: back to 0 after the last key
} timeline;

void timeline_init(timeline* tl);
void timeline_destroy(timeline* tl);
void timeline_clear(timeline* tl);   // every track removed; time back to 0

// The last key's time over every track; 0 when empty.
f32 timeline_duration(const timeline* tl);

// How many floats `component`.`field` holds, after checking it can be
// animated: a number, vec3 or colour that isn't set through a setter. 0
// (with `error` filled) otherwise.
uint32 timeline_field_width(const char* component, const char* field, char* error, size_t error_size);

timeline_track* timeline_find_track(timeline* tl, const char* entity, const char* component, const char* field);

// Replaces the track's keys (creating the track) with `keys`, which may come
// in any order. False, and no change, if the field can't be animated, a key
// is at a negative time, or two keys share a time.
b8 timeline_set_track(timeline* tl, const char* entity, const char* component, const char* field,
                      const timeline_key* keys, uint32 key_count, char* error, size_t error_size);

// Adds one key (creating the track), replacing any key at the same time.
b8 timeline_add_key(timeline* tl, const char* entity, const char* component, const char* field,
                    const timeline_key* key, char* error, size_t error_size);

// Removes the tracks that match: `component` and `field` may be NULL for
// "all". Returns how many were removed.
uint32 timeline_remove_tracks(timeline* tl, const char* entity, const char* component, const char* field);

// The track's value at time `t` (held before the first key and after the last).
void timeline_sample(const timeline_track* track, f32 t, f32 out[TIMELINE_VALUE_MAX]);

// Writes every track's value at `t` into `w`, and makes `t` the timeline's
// time. Returns how many tracks were written; tracks whose entity doesn't
// exist or lacks the component are skipped and counted in *out_skipped
// (may be NULL). Call world_update() afterwards.
uint32 timeline_evaluate(timeline* tl, world* w, f32 t, uint32* out_skipped);

// JSON: { "duration": s, "tracks": [ { "entity", "component", "field",
//   "keys": [ { "t": s, "value": n | [x, y, z], "ease": "in_out", "bezier": [...] } ] } ] }
// "ease" defaults to "linear"; "bezier" only with "bezier".
cJSON* timeline_to_json(const timeline* tl);
cJSON* timeline_track_to_json(const timeline_track* track);

// One key from JSON for a field `width` floats wide. Only reads it: its
// time, range and so on are checked when it goes into a track. False with
// `error` filled.
b8 timeline_key_from_json(const cJSON* json, uint32 width, timeline_key* out, char* error, size_t error_size);

// timeline_set_track() with the keys as a JSON array; errors name the key
// ("keys[2]: ...").
b8 timeline_set_track_json(timeline* tl, const char* entity, const char* component, const char* field,
                           const cJSON* keys, char* error, size_t error_size);

// Replaces every track with the ones in `json` (timeline_to_json()'s
// shape). All-or-nothing: on false the timeline is unchanged.
b8 timeline_from_json(timeline* tl, const cJSON* json, char* error, size_t error_size);

// The timeline as a JSON file at `path`. False (logged) if it can't be written.
b8 timeline_save(const timeline* tl, const char* path);

// Replaces the timeline with the file at `path`; a missing file is an empty
// timeline. False (logged), and no change, if the file isn't a valid timeline.
b8 timeline_load(timeline* tl, const char* path);
