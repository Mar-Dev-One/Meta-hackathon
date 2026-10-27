// The shot commands (Studio.h lists them): frames to PNG files, and where an
// entity lands in the frame. They leave the timeline at the time it was at.

#include "ShotCommands.h"

#include "Common/Json.h"
#include "Core/FileIO.h"
#include "Core/Paths.h"
#include "Shot.h"
#include "Studio/Studio.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define PREVIEW_WIDTH   960
#define PREVIEW_HEIGHT  540
#define PREVIEW_SAMPLES 8
#define RENDER_WIDTH    1920
#define RENDER_HEIGHT   1080
#define RENDER_SAMPLES  16
#define RENDER_FPS      30

// The file names shot.render writes, as ffmpeg's -i takes them.
#define FRAME_PATTERN "frame_%05d.png"

static f64
now_seconds(void)
{
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return (f64)ts.tv_sec + (f64)ts.tv_nsec * 1e-9;
}

// Puts the timeline back at `t` (rendering moves it).
static void
restore_time(studio* s, f32 t)
{
    timeline_evaluate(&s->timeline, s->w, t, NULL);
    world_update(s->w);
}

// width, height and samples from args, with defaults. False (error filled) if invalid.
static b8
read_size(const cJSON* args, uint16 default_width, uint16 default_height, uint32 default_samples,
          uint16* width, uint16* height, uint32* samples, char* error, size_t error_size)
{
    f32 w = default_width, h = default_height, n = (f32)default_samples;
    if (arg_number(args, "width", 16, SHOT_MAX_SIZE, &w, error, error_size) < 0
        || arg_number(args, "height", 16, SHOT_MAX_SIZE, &h, error, error_size) < 0
        || arg_number(args, "samples", 1, SHOT_MAX_SAMPLES, &n, error, error_size) < 0)
        return false;
    *width   = (uint16)w;
    *height  = (uint16)h;
    *samples = (uint32)n;
    return true;
}

// The folder to write into: args' "out_dir" (made if missing), or
// renders/<fallback> next to the executable.
static b8
read_out_dir(const cJSON* args, const char* fallback, char* out, size_t out_size, char* error, size_t error_size)
{
    const char* dir = NULL;
    if (arg_string(args, "out_dir", &dir, error, error_size) < 0)
        return false;
    if (dir)
        snprintf(out, out_size, "%s", dir);
    else
    {
        const char* exe_dir = paths_executable_dir();
        snprintf(out, out_size, "%s%srenders/%s", exe_dir, *exe_dir ? "/" : "", fallback);
    }
    if (!file_is_directory(out) && !file_make_directories(out))
        return set_error(error, error_size, "couldn't make the folder %s", out);
    return true;
}

// --- shot.preview -----------------------------------------------------------------------

static b8
cmd_preview(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    const cJSON* times = cJSON_GetObjectItemCaseSensitive(args, "times");
    int          count = cJSON_IsArray(times) ? cJSON_GetArraySize(times) : 0;
    if (count < 1 || count > 32)
        return set_error(error, error_size, "\"times\" must be an array of 1 to 32 times in seconds, e.g. [0, 2.5, 5]");
    const cJSON* t;
    cJSON_ArrayForEach(t, times)
    {
        if (!cJSON_IsNumber(t) || !isfinite(t->valuedouble) || t->valuedouble < 0.0)
            return set_error(error, error_size, "\"times\" must hold times of 0 or more seconds");
    }

    uint16 width, height;
    uint32 samples;
    char   dir[1024];
    if (!read_size(args, PREVIEW_WIDTH, PREVIEW_HEIGHT, PREVIEW_SAMPLES, &width, &height, &samples, error, error_size)
        || !read_out_dir(args, "preview", dir, sizeof(dir), error, error_size))
        return false;

    f32    previous = s->timeline.time;
    uint8* pixels   = malloc((size_t)width * height * 4);
    cJSON* frames   = cJSON_CreateArray();
    b8     ok       = true;
    cJSON_ArrayForEach(t, times)
    {
        char path[1200];
        snprintf(path, sizeof(path), "%s/t_%08.3f.png", dir, t->valuedouble);
        ok = shot_render_frame(&s->shots, s, (f32)t->valuedouble, width, height, samples, pixels, error, error_size)
             && shot_write_png(path, pixels, width, height, error, error_size);
        if (!ok)
            break;
        cJSON* frame = cJSON_CreateObject();
        cJSON_AddNumberToObject(frame, "t", t->valuedouble);
        cJSON_AddStringToObject(frame, "path", path);
        cJSON_AddItemToArray(frames, frame);
    }
    free(pixels);
    restore_time(s, previous);
    if (!ok)
    {
        cJSON_Delete(frames);
        return false;
    }

    *out_result = cJSON_CreateObject();
    cJSON_AddNumberToObject(*out_result, "width", width);
    cJSON_AddNumberToObject(*out_result, "height", height);
    cJSON_AddItemToObject(*out_result, "frames", frames);
    return true;
}

// --- shot.render ------------------------------------------------------------------------

static b8
cmd_render(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    f32 start = 0.0f, end = timeline_duration(&s->timeline), fps = RENDER_FPS;
    if (arg_number(args, "start", 0.0f, 3600.0f, &start, error, error_size) < 0
        || arg_number(args, "end", 0.0f, 3600.0f, &end, error, error_size) < 0
        || arg_number(args, "fps", 1.0f, 120.0f, &fps, error, error_size) < 0)
        return false;
    if (end < start)
        return set_error(error, error_size, "\"end\" (%g) is before \"start\" (%g)", end, start);

    uint16      width, height;
    uint32      samples;
    const char* video_path = NULL;
    char        dir[1024]  = "";
    if (!read_size(args, RENDER_WIDTH, RENDER_HEIGHT, RENDER_SAMPLES, &width, &height, &samples, error, error_size)
        || arg_string(args, "video", &video_path, error, error_size) < 0)
        return false;
    if (video_path && cJSON_GetObjectItemCaseSensitive(args, "out_dir"))
        return set_error(error, error_size, "give \"video\" (an .mp4) or \"out_dir\" (PNG frames), not both");
    if (!video_path && !read_out_dir(args, "shot", dir, sizeof(dir), error, error_size))
        return false;

    // A camera now, rather than an empty video after ffmpeg has started.
    camera check;
    if (!studio_camera_view(s, 1.0f, &check))
        return set_error(error, error_size, "there's no active camera: make one with camera.set");

    shot_video* video = video_path ? shot_video_open(video_path, width, height, fps, error, error_size) : NULL;
    if (video_path && !video)
        return false;

    // Frame i shows start + i / fps; the last one is at or just before `end`.
    uint32 count    = (uint32)floor((end - start) * fps + 1e-4) + 1;
    f32    previous = s->timeline.time;
    uint8* pixels   = malloc((size_t)width * height * 4);
    f64    began    = now_seconds();
    b8     ok       = true;
    for (uint32 i = 0; ok && i < count; ++i)
    {
        ok = shot_render_frame(&s->shots, s, start + (f32)i / fps, width, height, samples, pixels, error, error_size);
        if (ok && video)
            ok = shot_video_write(video, pixels, error, error_size);
        else if (ok)
        {
            char path[1200];
            snprintf(path, sizeof(path), "%s/" FRAME_PATTERN, dir, i);
            ok = shot_write_png(path, pixels, width, height, error, error_size);
        }
    }
    free(pixels);
    restore_time(s, previous);

    // Close even after a failure (that ends ffmpeg), keeping the first error.
    char close_error[256] = "";
    if (video && !shot_video_close(video, close_error, sizeof(close_error)) && ok)
        ok = set_error(error, error_size, "%s", close_error);
    if (!ok)
        return false;

    *out_result = cJSON_CreateObject();
    if (video_path)
        cJSON_AddStringToObject(*out_result, "video", video_path);
    else
    {
        cJSON_AddStringToObject(*out_result, "out_dir", dir);
        cJSON_AddStringToObject(*out_result, "pattern", FRAME_PATTERN);
    }
    cJSON_AddNumberToObject(*out_result, "frames", count);
    cJSON_AddNumberToObject(*out_result, "fps", fps);
    cJSON_AddNumberToObject(*out_result, "width", width);
    cJSON_AddNumberToObject(*out_result, "height", height);
    cJSON_AddNumberToObject(*out_result, "seconds", json_round6((f32)(now_seconds() - began)));
    return true;
}

// --- shot.bounds ------------------------------------------------------------------------

static b8
cmd_bounds(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;

    const char* name = NULL;
    f32 t = s->timeline.time, width = RENDER_WIDTH, height = RENDER_HEIGHT;
    if (arg_string(args, "entity", &name, error, error_size) <= 0)
        return set_error(error, error_size, "\"entity\" must name an entity with a MeshRenderer");
    if (arg_number(args, "t", 0.0f, 3600.0f, &t, error, error_size) < 0
        || arg_number(args, "width", 16, SHOT_MAX_SIZE, &width, error, error_size) < 0
        || arg_number(args, "height", 16, SHOT_MAX_SIZE, &height, error, error_size) < 0)
        return false;

    f32 previous = s->timeline.time;
    restore_time(s, t);   // the scene at t

    entity_id e = world_find(s->w, name);
    vec3      lo, hi;
    camera    cam;
    b8        has_bounds = e && world_bounds(s->w, e, lo, hi);
    b8        has_camera = studio_camera_view(s, width / height, &cam);
    if (!has_bounds || !has_camera)
    {
        restore_time(s, previous);
        return has_camera ? set_error(error, error_size, "\"%s\" isn't an entity with a MeshRenderer and a model", name)
                          : set_error(error, error_size, "there's no active camera: make one with camera.set");
    }

    // The bounding box's 8 corners on screen, 0..1 from the top-left. The box
    // is a little larger than the object, so this errs towards "cut".
    f32 x0 = INFINITY, y0 = INFINITY, x1 = -INFINITY, y1 = -INFINITY;
    uint32 behind = 0;
    for (int c = 0; c < 8; ++c)
    {
        vec3 p = { (c & 1) ? hi[0] : lo[0], (c & 2) ? hi[1] : lo[1], (c & 4) ? hi[2] : lo[2] };
        f32  x, y;
        if (!camera_world_to_screen(&cam, p, 1.0f, 1.0f, &x, &y))
        {
            ++behind;
            continue;
        }
        x0 = fminf(x0, x); y0 = fminf(y0, y);
        x1 = fmaxf(x1, x); y1 = fmaxf(y1, y);
    }
    restore_time(s, previous);

    *out_result = cJSON_CreateObject();
    if (behind == 8)
    {
        cJSON_AddBoolToObject(*out_result, "in_view", false);
        cJSON_AddStringToObject(*out_result, "reason", "behind the camera");
        return true;
    }

    // What's inside the frame, and which edges cut it.
    f32 cx0 = fmaxf(x0, 0.0f), cy0 = fmaxf(y0, 0.0f), cx1 = fminf(x1, 1.0f), cy1 = fminf(y1, 1.0f);
    b8  in_view = cx1 > cx0 && cy1 > cy0;
    cJSON_AddBoolToObject(*out_result, "in_view", in_view);
    json_add_floats(*out_result, "box", (f32[]){ x0, y0, x1, y1 }, 4);
    json_add_floats(*out_result, "center", (f32[]){ 0.5f * (x0 + x1), 0.5f * (y0 + y1) }, 2);
    cJSON_AddNumberToObject(*out_result, "fill", json_round6(in_view ? (cx1 - cx0) * (cy1 - cy0) : 0.0f));

    cJSON* cut = cJSON_AddArrayToObject(*out_result, "cut_by");
    if (x0 < 0.0f) cJSON_AddItemToArray(cut, cJSON_CreateString("left"));
    if (x1 > 1.0f) cJSON_AddItemToArray(cut, cJSON_CreateString("right"));
    if (y0 < 0.0f) cJSON_AddItemToArray(cut, cJSON_CreateString("top"));
    if (y1 > 1.0f) cJSON_AddItemToArray(cut, cJSON_CreateString("bottom"));
    if (behind) cJSON_AddItemToArray(cut, cJSON_CreateString("camera"));   // partly behind it
    return true;
}

// --- Table ----------------------------------------------------------------------------

static const cmd_arg PREVIEW_ARGS[] = {
    { "times", "array", true, "times in seconds, e.g. [0, 2.5, 5] (1 to 32)" },
    { "width", "number", false, "pixels (default 960)" },
    { "height", "number", false, "pixels (default 540)" },
    { "samples", "number", false, "sub-frames per frame for antialiasing, 1 to 64 (default 8)" },
    { "out_dir", "string", false, "folder for the PNGs (default renders/preview next to the Studio)" },
};

static const cmd_arg RENDER_ARGS[] = {
    { "start", "number", false, "seconds (default 0)" },
    { "end", "number", false, "seconds (default the timeline's duration)" },
    { "fps", "number", false, "frames per second (default 30)" },
    { "width", "number", false, "pixels (default 1920)" },
    { "height", "number", false, "pixels (default 1080)" },
    { "samples", "number", false, "sub-frames per frame for antialiasing, 1 to 64 (default 16)" },
    { "video", "string", false, "an .mp4 or .mov file to write directly (needs ffmpeg on the PATH); the fast way" },
    { "out_dir", "string", false, "instead of video: a folder for frame_00000.png ... (default renders/shot next to the Studio)" },
};

static const cmd_arg BOUNDS_ARGS[] = {
    { "entity", "string", true, "an entity with a MeshRenderer (the product)" },
    { "t", "number", false, "seconds (default the timeline's current time)" },
    { "width", "number", false, "the frame's width, for its shape (default 1920)" },
    { "height", "number", false, "the frame's height (default 1080)" },
};

#define COUNT_OF(a) (uint32)(sizeof(a) / sizeof((a)[0]))

static const cmd_host_command SHOT_COMMANDS[] = {
    { "shot.preview", "Renders the frames at the given times as PNGs, through the active camera; returns their paths.",
      PREVIEW_ARGS, COUNT_OF(PREVIEW_ARGS), false, cmd_preview },
    { "shot.render", "Renders every frame from start to end at fps into a video file, or as frame_00000.png, frame_00001.png, ...",
      RENDER_ARGS, COUNT_OF(RENDER_ARGS), false, cmd_render },
    { "shot.bounds", "Where an entity is in the frame at time t: its box (0..1 from the top-left), centre, "
                     "how much of the frame it fills, and which edges cut it.",
      BOUNDS_ARGS, COUNT_OF(BOUNDS_ARGS), false, cmd_bounds },
};

const cmd_host_command*
shot_commands(uint32* out_count)
{
    *out_count = COUNT_OF(SHOT_COMMANDS);
    return SHOT_COMMANDS;
}
