#pragma once

#include "Core/Defines.h"
#include "RHI/RHI.h"
#include "Renderer/SceneRenderer.h"

// Frames of a shot, rendered offscreen at any size -- independent of the
// window -- and read back as pixels: what becomes the video, and what the
// critic looks at.
//
// A frame is a function of the time it shows. Rendering one evaluates the
// studio's timeline at that time, then draws `samples` sub-frames from the
// active camera with TAA starting afresh, so each sub-frame adds a new
// sub-pixel position and the frame never depends on the one rendered before
// it: re-rendering one frame gives the same pixels as rendering it in sequence.

struct studio;

// A frame needs at most this many sub-frames (TAA keeps ~10% of each new one,
// so past ~32 nothing changes).
#define SHOT_MAX_SAMPLES 64
#define SHOT_MAX_SIZE    4096

// The shot's own scene renderer and colour target, made at the first frame
// and remade when the size changes. Its TAA history and shadow caches are
// separate from the window's, so rendering a shot doesn't disturb the view.
typedef struct shot_renderer
{
    scene_renderer  renderer;
    rhi_framebuffer target;   // RGBA8, the frame's size
    uint16          width;    // 0 = nothing made yet
    uint16          height;
} shot_renderer;

void shot_renderer_destroy(shot_renderer* r);

// Renders the studio's scene at time `t` into `out_pixels` (width * height
// * 4 bytes, RGBA8, rows bottom-up as rhi_read_pixels() gives them). Leaves
// the timeline evaluated at `t`. False (error filled) if there's no active
// camera or the size is out of range.
b8 shot_render_frame(shot_renderer* r, struct studio* s, f32 t, uint16 width, uint16 height, uint32 samples,
                     uint8* out_pixels, char* error, size_t error_size);

// Writes bottom-up RGBA8 pixels as a PNG file. False (error filled) on failure.
// PNG compression is slow for big frames (~0.6 s at 1080p): fine for
// previews, too slow for a whole sequence -- that goes to shot_video.
b8 shot_write_png(const char* path, const uint8* pixels, uint16 width, uint16 height, char* error, size_t error_size);

// A video file being written by ffmpeg (which must be on the PATH): frames
// are piped to it raw, so nothing is compressed twice and no frame files
// are left behind. H.264, yuv420p (plays everywhere), CRF 16.
typedef struct shot_video shot_video;

// Starts ffmpeg writing `path` (.mp4 or .mov). NULL (error filled) if it can't start.
shot_video* shot_video_open(const char* path, uint16 width, uint16 height, f32 fps, char* error, size_t error_size);

// Adds one frame: width * height * 4 bytes, RGBA8, rows bottom-up.
b8 shot_video_write(shot_video* video, const uint8* pixels, char* error, size_t error_size);

// Finishes the file and waits for ffmpeg. False (error filled) if ffmpeg
// failed -- the file is then incomplete. Frees `video` either way.
b8 shot_video_close(shot_video* video, char* error, size_t error_size);
