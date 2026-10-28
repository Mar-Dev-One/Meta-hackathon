#include "Shot.h"

#include "Common/Json.h"
#include "Core/Image.h"
#include "Studio/Studio.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
    #define popen  _popen
    #define pclose _pclose
#endif

// The shot renderer's shadows, as the app's own view has them.
#define SHOT_CASCADE_COUNT   4
#define SHOT_SHADOW_MAP_SIZE 2048

void
shot_renderer_destroy(shot_renderer* r)
{
    if (r->width)
    {
        rhi_framebuffer_destroy(r->target);
        scene_renderer_destroy(&r->renderer);
    }
    r->width = r->height = 0;
}

// Makes the renderer and target `width` x `height`, remaking them if the size changed.
static b8
ensure_size(shot_renderer* r, uint16 width, uint16 height, char* error, size_t error_size)
{
    if (r->width == width && r->height == height)
        return true;

    shot_renderer_destroy(r);
    if (!scene_renderer_create(&r->renderer, width, height, SHOT_CASCADE_COUNT, SHOT_SHADOW_MAP_SIZE))
        return set_error(error, error_size, "couldn't make a %ux%u renderer", width, height);

    rhi_framebuffer_attachment color = { .format = RHI_FORMAT_RGBA8 };
    r->target = rhi_framebuffer_create((rhi_framebuffer_desc){
        .width                  = width,
        .height                 = height,
        .color_attachments      = &color,
        .color_attachment_count = 1,
    });
    r->width  = width;
    r->height = height;
    return true;
}

b8
shot_render_frame(shot_renderer* r, studio* s, f32 t, uint16 width, uint16 height, uint32 samples,
                  uint8* out_pixels, char* error, size_t error_size)
{
    if (width < 16 || height < 16 || width > SHOT_MAX_SIZE || height > SHOT_MAX_SIZE)
        return set_error(error, error_size, "a frame is 16 to %d pixels a side (got %ux%u)", SHOT_MAX_SIZE, width, height);

    studio_evaluate(s, t, NULL);

    camera cam;
    if (!studio_camera_view(s, (f32)width / (f32)height, &cam))
        return set_error(error, error_size, "there's no active camera: make one with camera.set");
    if (!ensure_size(r, width, height, error, error_size))
        return false;

    if (s->ibl)
        ibl_cache_sync(s->ibl, s->env->hdri);
    scene_render_settings settings;
    studio_render_settings(s, &settings);

    // TAA from a clean start: no history, the jitter sequence from its first
    // step, no previous camera. These are scene_renderer's and
    // post_process's own state (Renderer/SceneRenderer.h, PostProcess.h).
    r->renderer.post.taa_valid = false;
    r->renderer.taa_frame      = 0;
    r->renderer.has_previous   = false;
    if (settings.antialiasing != SCENE_AA_TAA)
        samples = 1;   // without TAA every sub-frame is the same picture
    samples = samples < 1 ? 1 : samples > SHOT_MAX_SAMPLES ? SHOT_MAX_SAMPLES : samples;

    for (uint32 i = 0; i < samples; ++i)
    {
        settings.delta_time = i == 0 ? -1.0f : 0.0f;   // auto-exposure settles at once, then holds
        scene_renderer_draw_to(&r->renderer, s->w, &cam, &settings, r->target);
    }

    // Titles over the finished picture, then the pixels.
    rhi_framebuffer_bind(r->target);
    text_layer_draw(&s->texts, width, height);
    rhi_read_pixels(0, 0, width, height, out_pixels);
    rhi_framebuffer_bind_default();
    return true;
}

b8
shot_write_png(const char* path, const uint8* pixels, uint16 width, uint16 height, char* error, size_t error_size)
{
    size_t size = 0;
    uint8* png  = image_encode_png(pixels, width, height, 4, &size);
    FILE*  file = png ? fopen(path, "wb") : NULL;
    b8     ok   = file && fwrite(png, 1, size, file) == size;
    if (file)
        ok = fclose(file) == 0 && ok;
    free(png);
    return ok || set_error(error, error_size, "couldn't write %s", path);
}

struct shot_video
{
    FILE*  pipe;        // ffmpeg's stdin
    size_t frame_size;  // bytes per frame
};

shot_video*
shot_video_open(const char* path, uint16 width, uint16 height, f32 fps, char* error, size_t error_size)
{
    const char* extension = strrchr(path, '.');
    if (!extension || (strcmp(extension, ".mp4") != 0 && strcmp(extension, ".mov") != 0))
        return set_error(error, error_size, "the video must be a .mp4 or .mov file (got %s)", path), NULL;
    if (strchr(path, '"'))
        return set_error(error, error_size, "the video's path can't contain quotes"), NULL;

    // Raw RGBA in on stdin, flipped (rows come bottom-up), H.264 out.
    // Only the path is quoted: cmd.exe mangles a command line that starts
    // with a quote and has more than two.
    char command[1400];
    snprintf(command, sizeof(command),
             "ffmpeg -y -loglevel error -f rawvideo -pix_fmt rgba -s %ux%u -r %g -i - "
             "-vf vflip -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -movflags +faststart \"%s\"",
             width, height, fps, path);

    FILE* pipe = popen(command, "wb");
    if (!pipe)
        return set_error(error, error_size, "couldn't start ffmpeg"), NULL;

    shot_video* video = malloc(sizeof(*video));
    video->pipe       = pipe;
    video->frame_size = (size_t)width * height * 4;
    return video;
}

b8
shot_video_write(shot_video* video, const uint8* pixels, char* error, size_t error_size)
{
    if (fwrite(pixels, 1, video->frame_size, video->pipe) != video->frame_size)
        return set_error(error, error_size, "ffmpeg stopped taking frames (is it installed and on the PATH?)");
    return true;
}

b8
shot_video_close(shot_video* video, char* error, size_t error_size)
{
    int status = pclose(video->pipe);
    free(video);
    return status == 0
           || set_error(error, error_size, "ffmpeg failed (exit %d): is it installed and on the PATH? its messages are on the Studio's console", status);
}
