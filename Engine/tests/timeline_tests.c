// Tests for Timeline/Timeline.h: easing, sampling, track editing, writing
// into a World and JSON. No window or GPU needed.
//
//   ctest --test-dir build -C Release      (or run Timeline_Tests.exe)

#include "Assets/AssetCache.h"
#include "Timeline/Timeline.h"
#include "World/World.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond)                                                       \
    do {                                                                  \
        if (!(cond))                                                      \
        {                                                                 \
            printf("FAILED %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
            ++failures;                                                   \
        }                                                                 \
    } while (0)

#define CHECK_NEAR(a, b) CHECK(fabsf((f32)(a) - (f32)(b)) < 1e-3f)

static timeline_key
key1(f32 t, f32 v, timeline_ease ease)
{
    return (timeline_key){ .time = t, .value = { v }, .ease = ease };
}

static void
test_easing(void)
{
    const f32 none[4] = { 0 };
    for (int e = 0; e < EASE_COUNT; ++e)
    {
        CHECK_NEAR(timeline_ease_apply((timeline_ease)e, none, 0.0f), 0.0f);
        CHECK_NEAR(timeline_ease_apply((timeline_ease)e, none, 1.0f), 1.0f);
    }
    CHECK_NEAR(timeline_ease_apply(EASE_LINEAR, none, 0.3f), 0.3f);
    CHECK_NEAR(timeline_ease_apply(EASE_IN_OUT, none, 0.5f), 0.5f);   // symmetric
    CHECK(timeline_ease_apply(EASE_IN, none, 0.5f) < 0.4f);
    CHECK(timeline_ease_apply(EASE_OUT, none, 0.5f) > 0.6f);
    CHECK(timeline_ease_apply(EASE_IN_OUT, none, 0.1f) < 0.1f);
    CHECK_NEAR(timeline_ease_apply(EASE_STEP, none, 0.99f), 0.0f);

    const f32 straight[4] = { 0.25f, 0.25f, 0.75f, 0.75f };   // a bezier that is a straight line
    CHECK_NEAR(timeline_ease_apply(EASE_BEZIER, straight, 0.3f), 0.3f);

    timeline_ease ease;
    CHECK(timeline_ease_from_name("in_out", &ease) && ease == EASE_IN_OUT);
    CHECK(!timeline_ease_from_name("bounce", &ease));
}

static void
test_tracks(void)
{
    timeline tl;
    timeline_init(&tl);
    char error[256];

    // Keys in any order come out sorted.
    timeline_key keys[] = { key1(2.0f, 10.0f, EASE_LINEAR), key1(0.0f, 0.0f, EASE_LINEAR) };
    CHECK(timeline_set_track(&tl, "cam", "Camera", "fov_degrees", keys, 2, error, sizeof(error)));
    timeline_track* track = timeline_find_track(&tl, "cam", "Camera", "fov_degrees");
    CHECK(track && track->key_count == 2 && track->width == 1 && track->keys[0].time == 0.0f);

    f32 v[TIMELINE_VALUE_MAX];
    timeline_sample(track, -1.0f, v); CHECK_NEAR(v[0], 0.0f);    // held before the first key
    timeline_sample(track, 1.0f, v);  CHECK_NEAR(v[0], 5.0f);
    timeline_sample(track, 9.0f, v);  CHECK_NEAR(v[0], 10.0f);   // held after the last
    CHECK_NEAR(timeline_duration(&tl), 2.0f);

    // add_key inserts in order and replaces a key at the same time.
    timeline_key mid = key1(1.0f, 100.0f, EASE_STEP);
    CHECK(timeline_add_key(&tl, "cam", "Camera", "fov_degrees", &mid, error, sizeof(error)));
    CHECK(track->key_count == 3 && track->keys[1].value[0] == 100.0f);
    timeline_sample(track, 1.5f, v); CHECK_NEAR(v[0], 100.0f);   // step holds
    mid.value[0] = 50.0f;
    CHECK(timeline_add_key(&tl, "cam", "Camera", "fov_degrees", &mid, error, sizeof(error)));
    CHECK(track->key_count == 3 && track->keys[1].value[0] == 50.0f);

    // Rejected, with nothing changed.
    CHECK(!timeline_set_track(&tl, "cam", "Lens", "fov", keys, 2, error, sizeof(error)));
    CHECK(strstr(error, "Transform") != NULL);                          // lists the components
    CHECK(!timeline_set_track(&tl, "cam", "MeshRenderer", "visible", keys, 2, error, sizeof(error)));   // a bool
    CHECK(!timeline_set_track(&tl, "cam", "MeshRenderer", "model", keys, 2, error, sizeof(error)));     // via setter
    timeline_key same[] = { key1(1.0f, 0.0f, EASE_LINEAR), key1(1.0f, 1.0f, EASE_LINEAR) };
    CHECK(!timeline_set_track(&tl, "cam", "Camera", "fov_degrees", same, 2, error, sizeof(error)));
    timeline_key negative = key1(-1.0f, 0.0f, EASE_LINEAR);
    CHECK(!timeline_add_key(&tl, "cam", "Camera", "fov_degrees", &negative, error, sizeof(error)));
    CHECK(track->key_count == 3);

    CHECK(timeline_field_width("Transform", "position", NULL, 0) == 3);
    CHECK(timeline_field_width("Light", "color", NULL, 0) == 3);
    CHECK(timeline_field_width("MeshRenderer", "material.roughness", NULL, 0) == 1);

    CHECK(timeline_remove_tracks(&tl, "cam", NULL, NULL) == 1 && tl.track_count == 0);
    timeline_destroy(&tl);
}

static void
test_evaluate(void)
{
    asset_cache assets;
    world       w;
    assets_init(&assets);
    world_init(&w, &assets);

    entity_id box = world_create(&w, "box");
    world_add_mesh_renderer(&w, box, ASSET_NONE);

    timeline tl;
    timeline_init(&tl);
    char error[256];

    timeline_key move[] = {
        { .time = 0.0f, .value = { 0.0f, 0.0f, 0.0f } },
        { .time = 2.0f, .value = { 2.0f, 4.0f, -6.0f } },
    };
    CHECK(timeline_set_track(&tl, "box", "Transform", "position", move, 2, error, sizeof(error)));
    timeline_key rough[] = { key1(0.0f, 0.2f, EASE_LINEAR), key1(1.0f, 3.0f, EASE_LINEAR) };   // past roughness' max of 1
    CHECK(timeline_set_track(&tl, "box", "MeshRenderer", "material.roughness", rough, 2, error, sizeof(error)));
    timeline_key ghost[] = { key1(0.0f, 1.0f, EASE_LINEAR) };
    CHECK(timeline_set_track(&tl, "nobody", "Camera", "fov_degrees", ghost, 1, error, sizeof(error)));

    uint32 skipped = 0;
    uint32 written = timeline_evaluate(&tl, &w, 1.0f, &skipped);
    CHECK(written == 2 && skipped == 1 && tl.time == 1.0f);

    const c_transform* t = world_transform(&w, box);
    CHECK_NEAR(t->position[0], 1.0f);
    CHECK_NEAR(t->position[1], 2.0f);
    CHECK_NEAR(t->position[2], -3.0f);

    const c_mesh_renderer* mr = world_mesh_renderer(&w, box);
    CHECK_NEAR(mr->material.roughness, 1.0f);                      // clamped to the field's range
    CHECK(mr->material.fields & MATERIAL_OVERRIDE_ROUGHNESS);       // and the override switched on

    // JSON round trip, and the loader's all-or-nothing rule.
    cJSON* json = timeline_to_json(&tl);
    timeline copy;
    timeline_init(&copy);
    CHECK(timeline_from_json(&copy, json, error, sizeof(error)));
    CHECK(copy.track_count == 3);
    timeline_track* moved = timeline_find_track(&copy, "box", "Transform", "position");
    CHECK(moved && moved->key_count == 2 && moved->keys[1].value[2] == -6.0f);

    cJSON* bad = cJSON_Parse("{\"tracks\": [{\"entity\": \"box\", \"component\": \"Transform\", "
                             "\"field\": \"position\", \"keys\": [{\"t\": 0, \"value\": 1}]}]}");
    CHECK(!timeline_from_json(&copy, bad, error, sizeof(error)));   // a number for a vec3
    CHECK(copy.track_count == 3);
    cJSON_Delete(bad);
    cJSON_Delete(json);

    timeline_key k;
    cJSON* key = cJSON_Parse("{\"t\": 1, \"value\": 2, \"ease\": \"bezier\", \"bezier\": [0.1, 0.8, 0.2, 1]}");
    CHECK(timeline_key_from_json(key, 1, &k, error, sizeof(error)) && k.ease == EASE_BEZIER && k.bezier[1] == 0.8f);
    cJSON_Delete(key);
    key = cJSON_Parse("{\"t\": 1, \"value\": 2, \"speed\": 3}");
    CHECK(!timeline_key_from_json(key, 1, &k, error, sizeof(error)));   // unknown key field
    cJSON_Delete(key);

    timeline_destroy(&copy);
    timeline_destroy(&tl);
    world_shutdown(&w);
    assets_shutdown(&assets);
}

int main(void)
{
    test_easing();
    test_tracks();
    test_evaluate();
    if (failures)
    {
        printf("%d check(s) failed\n", failures);
        return 1;
    }
    printf("timeline tests passed\n");
    return 0;
}
