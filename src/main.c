// testbed/main.c
//
// The testbed: builds a scene in code with the engine's World API -- no scene
// file -- and draws it with the scene renderer. What a program using the
// engine as a library looks like, and a quick way to try a renderer change.
//
//   Testbed [--check PNG] [--view NAME] [--port N]
//     --check PNG   render a few frames in a hidden window, save the picture
//                   to PNG and exit (0 if it was written)
//     --view NAME   a debug view instead of the lit scene: albedo, normals,
//                   roughness, metallic, ao, shadow, lighting, wireframe,
//                   lights (Renderer/SceneRenderer.h)
//     --port N      the command server's port (default 7468)
//
// The command server (Net/CommandServer.h) runs while the window is open
// (not for --check): other processes drive the world over a localhost
// WebSocket with JSON-RPC, with undo history. Its URL, token included, is
// logged and written to server.json next to the executable.
//
// The scene (build_scene()): a ground plane; the material grid -- two rows
// of spheres, dielectric in front and metal behind, going from smooth to
// rough left to right; a polished Suzanne turning on a pedestal; a sun that
// casts shadows, a warm point light and a spot light; an HDRI sky. Models
// and the HDRI come from the assets/ folder next to the executable, which
// the build fills from Assets/models and Assets/hdri (use_bundled_assets()).
//
// Left-drag orbits, the wheel zooms, Esc quits.

#include "App.h"
#include "Assets/AssetCache.h"
#include "Commands/Commands.h"
#include "Commands/History.h"
#include "Core/Defines.h"
#include "Core/Image.h"
#include "Core/Paths.h"
#include "Net/CommandServer.h"
#include "Platform/Input.h"
#include "Platform/Window.h"
#include "Renderer/IBL.h"
#include "Renderer/Renderer.h"
#include "Renderer/SceneRenderer.h"
#include "Scene/Camera.h"
#include "Scene/Light.h"
#include "Scene/OrbitCamera.h"
#include "World/Environment.h"
#include "World/World.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HDRI "hdri/citrus_orchard_road_puresky_4k.hdr"

#define SHADOW_MAP_SIZE 2048
#define CASCADE_COUNT   4

// --check renders this many frames before the picture is taken, so the
// shadows and IBL settle.
#define CHECK_FRAMES 8

#define GRID_COLUMNS 7

typedef struct testbed_state
{
    const char*      check_path;
    uint32           check_frames;
    b8               check_passed;
    scene_debug_view debug_view;

    asset_cache       assets;
    world             world;
    scene_renderer    renderer;
    scene_environment env;
    ibl_cache         ibl;

    camera       cam;
    orbit_camera orbit;
    f32          aspect;

    // The command server; NULL for --check or if it couldn't start.
    uint16           server_port;
    char             discovery_path[1024];
    command_server*  server;
    command_context  commands;
    command_history  history;
} testbed_state;

// --- Scene -----------------------------------------------------------------------

// An entity showing `model` at `position`, uniformly scaled.
static entity_id
add_model(world* w, const char* name, asset_id model, vec3 position, f32 scale)
{
    entity_id    e = world_create(w, name);
    c_transform* t = world_transform(w, e);
    glm_vec3_copy(position, t->position);
    glm_vec3_fill(t->scale, scale);
    world_add_mesh_renderer(w, e, model);
    return e;
}

static void
set_material(world* w, entity_id e, vec3 base_color, f32 metallic, f32 roughness)
{
    material_override* m = &world_mesh_renderer(w, e)->material;
    m->fields    = MATERIAL_OVERRIDE_BASE_COLOR | MATERIAL_OVERRIDE_METALLIC | MATERIAL_OVERRIDE_ROUGHNESS;
    glm_vec3_copy(base_color, m->base_color);
    m->metallic  = metallic;
    m->roughness = roughness;
}

static void
build_scene(world* w, asset_cache* assets)
{
    asset_id plane  = assets_builtin(assets, BUILTIN_PLANE);
    asset_id cube   = assets_builtin(assets, BUILTIN_CUBE);
    asset_id sphere = assets_builtin(assets, BUILTIN_SPHERE);

    // Ground.
    entity_id ground = add_model(w, "ground", plane, (vec3){ 0.0f, 0.0f, 0.0f }, 1.0f);
    glm_vec3_copy((vec3){ 16.0f, 1.0f, 12.0f }, world_transform(w, ground)->scale);
    set_material(w, ground, (vec3){ 0.18f, 0.18f, 0.2f }, 0.0f, 0.85f);

    // The material grid: roughness 0.05 .. 1 across, dielectric (red) in
    // front, metal (gold) behind.
    for (int row = 0; row < 2; ++row)
    {
        for (int column = 0; column < GRID_COLUMNS; ++column)
        {
            char name[32];
            snprintf(name, sizeof(name), "%s_%d", row ? "metal" : "dielectric", column);

            f32 roughness = 0.05f + 0.95f * (f32)column / (f32)(GRID_COLUMNS - 1);
            f32 x         = ((f32)column - (GRID_COLUMNS - 1) * 0.5f) * 1.1f;
            f32 z         = row ? -1.2f : 0.0f;

            entity_id e = add_model(w, name, sphere, (vec3){ x, 0.45f, z }, 0.9f);
            if (row)
                set_material(w, e, (vec3){ 1.0f, 0.78f, 0.34f }, 1.0f, roughness);
            else
                set_material(w, e, (vec3){ 0.8f, 0.12f, 0.1f }, 0.0f, roughness);
        }
    }

    // A polished Suzanne turning on a pedestal, in front of the grid.
    entity_id pedestal = add_model(w, "pedestal", cube, (vec3){ 0.0f, 0.4f, 2.2f }, 1.0f);
    glm_vec3_copy((vec3){ 0.9f, 0.8f, 0.9f }, world_transform(w, pedestal)->scale);
    set_material(w, pedestal, (vec3){ 0.9f, 0.9f, 0.88f }, 0.0f, 0.4f);

    asset_id suzanne = assets_load_model(assets, "models/suzanne.obj");
    if (suzanne != ASSET_NONE)
    {
        entity_id head = add_model(w, "suzanne", suzanne, (vec3){ 0.0f, 0.0f, 0.0f }, 0.5f);
        set_material(w, head, (vec3){ 0.95f, 0.95f, 0.95f }, 1.0f, 0.12f);
        world_add_spin(w, head, (vec3){ 0.0f, 30.0f, 0.0f });

        // The mesh isn't centred on its origin: put its bounds' centre over
        // the pedestal and their bottom on its top.
        vec3 lo, hi;
        world_update(w);
        if (world_bounds(w, head, lo, hi))
        {
            c_transform* t  = world_transform(w, head);
            t->position[0] -= (lo[0] + hi[0]) * 0.5f - 0.0f;
            t->position[1] -= lo[1] - 0.8f;
            t->position[2] -= (lo[2] + hi[2]) * 0.5f - 2.2f;
        }
    }
    else
        LOG_WARN("testbed: models/suzanne.obj didn't load; the pedestal stays empty\n");

    // Lights: a sun from the upper left, a warm point light by the grid and
    // a cool spot light on the pedestal.
    light sun;
    light_init_directional(&sun, (vec3){ -0.4f, -1.0f, -0.5f }, (vec3){ 1.0f, 0.96f, 0.9f }, 3.0f);
    world_add_light(w, world_create(w, "sun"), sun);

    light warm;
    light_init_point(&warm, (vec3){ 1.0f, 0.6f, 0.3f }, 8.0f, 6.0f);
    entity_id lamp = world_create(w, "warm_lamp");
    glm_vec3_copy((vec3){ -3.5f, 1.5f, 1.0f }, world_transform(w, lamp)->position);
    world_add_light(w, lamp, warm);

    light spot;
    light_init_spot(&spot, (vec3){ 0.0f, -1.0f, 0.0f }, (vec3){ 0.6f, 0.75f, 1.0f }, 20.0f, 8.0f, 15.0f, 25.0f);
    entity_id spot_entity = world_create(w, "spot");
    glm_vec3_copy((vec3){ 0.0f, 4.0f, 2.2f }, world_transform(w, spot_entity)->position);
    world_add_light(w, spot_entity, spot);
}

// Points the orbit camera at the grid and the pedestal (not the whole ground,
// which would leave them small in the middle).
static void
frame_scene(testbed_state* state)
{
    vec3 lo = { -4.0f, 0.0f, -1.8f };
    vec3 hi = { 4.0f, 1.6f, 2.8f };

    camera_init(&state->cam, (vec3){ 0.0f, 0.0f, 0.0f }, (vec3){ 0.0f, 0.0f, 0.0f }, 45.0f, state->aspect, 0.1f, 100.0f);
    state->orbit = (orbit_camera){ .yaw = 20.0f, .pitch = 22.0f };
    orbit_fit(&state->orbit, &state->cam, lo, hi, 1.0f);
    orbit_apply(&state->orbit, &state->cam);
}

// --- Command server --------------------------------------------------------------

// Starts the server on the world, its environment and an undo history.
// Failing to start is logged and leaves the testbed running without it.
static void
start_server(testbed_state* state)
{
    const char* exe_dir = paths_executable_dir();
    snprintf(state->discovery_path, sizeof(state->discovery_path), "%s%sserver.json", exe_dir, *exe_dir ? "/" : "");

    server_config config = { .port = state->server_port, .discovery_path = state->discovery_path };
    state->server        = server_start(&config);
    if (!state->server)
        return;

    history_init(&state->history);
    state->commands = (command_context){
        .w              = &state->world,
        .history        = &state->history,
        .environment    = &state->env,
        .on_change      = server_on_change,
        .on_change_user = state->server,
    };
    LOG_INFO("testbed: command server at %s\n", server_url(state->server));
}

// --- App hooks -------------------------------------------------------------------

static void
on_init(App* app)
{
    testbed_state* state = (testbed_state*)app->user_data;
    window_size    size  = window_get_size(get_renderer()->drawing_window);
    state->aspect        = size.height ? (f32)size.width / (f32)size.height : 1.0f;

    if (!scene_renderer_create(&state->renderer, size.width, size.height, CASCADE_COUNT, SHADOW_MAP_SIZE))
        FATAL("testbed: failed to create the scene renderer");

    assets_init(&state->assets);
    world_init(&state->world, &state->assets);
    build_scene(&state->world, &state->assets);
    world_update(&state->world);
    LOG_INFO("testbed: built %u entities\n", world_count(&state->world));

    state->env = scene_environment_default();
    snprintf(state->env.hdri, sizeof(state->env.hdri), "%s", HDRI);
    ibl_cache_sync(&state->ibl, state->env.hdri);

    frame_scene(state);

    if (!state->check_path)
        start_server(state);
}

static void
on_resize(App* app, uint16 width, uint16 height)
{
    testbed_state* state = (testbed_state*)app->user_data;
    if (width == 0 || height == 0)   // minimized
        return;

    state->aspect = (f32)width / (f32)height;
    camera_set_aspect(&state->cam, state->aspect);
    scene_renderer_resize(&state->renderer, width, height);
}

// --check: the frame as a PNG at check_path. False (logged) if it can't be
// rendered or written.
static b8
save_check_picture(testbed_state* state, const scene_render_settings* settings)
{
    uint16 width, height;
    uint8* rgba = scene_renderer_capture(&state->renderer, &state->world, &state->cam, settings, &width, &height);
    if (!rgba)
    {
        LOG_ERROR("check: nothing was rendered\n");
        return false;
    }

    size_t png_size = 0;
    uint8* png      = image_encode_png(rgba, width, height, 4, &png_size);
    free(rgba);

    FILE* file = png ? fopen(state->check_path, "wb") : NULL;
    b8    ok   = file && fwrite(png, 1, png_size, file) == png_size;
    if (file)
        ok = fclose(file) == 0 && ok;
    free(png);

    if (ok)
        LOG_INFO("check: %s\n", state->check_path);
    else
        LOG_ERROR("check: couldn't write %s\n", state->check_path);
    return ok;
}

static void
on_frame(App* app, f32 dt)
{
    testbed_state* state = (testbed_state*)app->user_data;

    if (input_key_pressed(INPUT_KEY_ESCAPE))
        app->should_close = true;

    // Commands run here, on the main thread, before the frame is built. A
    // scene.load can change the HDRI, which the sync then bakes (a no-op
    // while it's unchanged).
    if (state->server)
    {
        server_poll(state->server, &state->commands);
        ibl_cache_sync(&state->ibl, state->env.hdri);
    }

    // A check's picture is the scene as built, whatever the frame times.
    if (!state->check_path)
        world_tick(&state->world, fminf(dt, 0.1f));
    world_update(&state->world);

    f32 dx = 0.0f, dy = 0.0f;
    if (input_mouse_down(INPUT_MOUSE_LEFT))
        input_mouse_delta(&dx, &dy);
    if (dx != 0.0f || dy != 0.0f)
        orbit_drag(&state->orbit, &state->cam, dx, dy);

    f32 wheel_x, wheel;
    input_scroll(&wheel_x, &wheel);
    if (wheel != 0.0f)
        orbit_zoom(&state->orbit, &state->cam, wheel);

    scene_render_settings settings = scene_render_settings_default();
    scene_render_settings_apply_environment(&settings, &state->env, ibl_cache_maps(&state->ibl));
    settings.debug_view = state->debug_view;
    settings.delta_time = state->check_path ? -1.0f : dt;

    scene_renderer_draw(&state->renderer, &state->world, &state->cam, &settings);

    if (state->check_path && ++state->check_frames >= CHECK_FRAMES)
    {
        state->check_passed = save_check_picture(state, &settings);
        app->should_close   = true;
    }
}

static void
on_shutdown(App* app)
{
    testbed_state* state = (testbed_state*)app->user_data;

    if (state->server)
    {
        server_stop(state->server);   // also removes server.json
        history_shutdown(&state->history, &state->world);
    }
    world_shutdown(&state->world);    // releases the world's assets...
    assets_shutdown(&state->assets);  // ...then the models themselves
    ibl_cache_destroy(&state->ibl);
    scene_renderer_destroy(&state->renderer);
}

// Makes <executable's folder>/assets the project root. Without it the engine
// falls back to assets/ under the working directory, which is only right
// when the program is started from its own folder. False (logged) if the
// folder is missing.
static b8
use_bundled_assets(void)
{
    char        directory[1024];
    const char* exe_dir = paths_executable_dir();
    snprintf(directory, sizeof(directory), "%s%sassets", exe_dir, *exe_dir ? "/" : "");

    if (paths_set_project_root(directory))
        return true;
    LOG_ERROR("testbed: no assets folder at %s\n", directory);
    return false;
}

static void
print_usage(void)
{
    printf("usage: Testbed [--check PNG] [--view NAME] [--port N]\n"
           "  --check  render the scene once, hidden, into PNG and exit (0 = it was written)\n"
           "  --view   a debug view: albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe, lights\n"
           "  --port   the command server's port (default %d; another free one if it's taken)\n",
           SERVER_DEFAULT_PORT);
}

int main(int argc, char** argv)
{
    testbed_state state = { 0 };

    for (int i = 1; i < argc; ++i)
    {
        const char* arg = argv[i];
        if (strcmp(arg, "--check") == 0)
        {
            state.check_path = i + 1 < argc ? argv[++i] : NULL;
            if (!state.check_path)
            {
                fprintf(stderr, "--check needs the PNG file to write\n");
                print_usage();
                return 1;
            }
        }
        else if (strcmp(arg, "--view") == 0)
        {
            if (!scene_debug_view_from_name(i + 1 < argc ? argv[++i] : NULL, &state.debug_view))
            {
                fprintf(stderr, "--view needs one of: lit, albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe, lights\n");
                print_usage();
                return 1;
            }
        }
        else if (strcmp(arg, "--port") == 0)
        {
            int port = i + 1 < argc ? atoi(argv[++i]) : 0;
            if (port <= 0 || port > 65535)
            {
                fprintf(stderr, "--port needs a port number (1-65535)\n");
                print_usage();
                return 1;
            }
            state.server_port = (uint16)port;
        }
        else if (strcmp(arg, "--help") == 0 || strcmp(arg, "-h") == 0)
        {
            print_usage();
            return 0;
        }
        else
        {
            fprintf(stderr, "unknown argument %s\n", arg);
            print_usage();
            return 1;
        }
    }

    if (!use_bundled_assets())
        return 1;

    App app = {
        .name       = "PBR Testbed",
        .hidden      = state.check_path != NULL,
        .width       = state.check_path ? 960 : 1600,
        .height      = state.check_path ? 540 : 900,
        .on_init     = on_init,
        .on_frame    = on_frame,
        .on_shutdown = on_shutdown,
        .on_resize   = on_resize,
        .user_data   = &state,
        .ui          = NULL
    };

    run(&app);
    terminate(&app);

    if (state.check_path)
        return state.check_passed ? 0 : 1;
    return 0;
}
