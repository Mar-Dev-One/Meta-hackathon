#include "Studio.h"

#include <math.h>
#include <string.h>

#define RAD_TO_DEG (180.0f / 3.14159265358979f)

static void
reset_render_settings(studio* s)
{
    scene_render_settings defaults = scene_render_settings_default();
    s->antialiasing = SCENE_AA_TAA;   // a product shot holds still long enough for TAA to settle
    s->shadows      = defaults.shadows;
    glm_vec3_copy(defaults.clear_color, s->clear_color);
    s->active_camera[0] = '\0';
}

void
studio_init(studio* s, world* w, scene_environment* env)
{
    memset(s, 0, sizeof(*s));
    s->w   = w;
    s->env = env;
    reset_render_settings(s);
}

void
studio_reset(studio* s)
{
    world_clear(s->w);
    *s->env = scene_environment_default();
    reset_render_settings(s);
}

void
studio_apply_render_settings(const studio* s, scene_render_settings* settings)
{
    settings->antialiasing = s->antialiasing;
    settings->shadows      = s->shadows;
    glm_vec3_copy((f32*)s->clear_color, settings->clear_color);
}

b8
studio_camera_view(const studio* s, f32 aspect, camera* out)
{
    if (!s->active_camera[0])
        return false;
    return world_camera_view(s->w, world_find(s->w, s->active_camera), aspect, out);
}

b8
studio_look_rotation(const vec3 direction, vec3 out_rotation_deg)
{
    vec3 d;
    glm_vec3_copy((f32*)direction, d);
    if (glm_vec3_norm(d) < 1e-6f)
        return false;
    glm_vec3_normalize(d);

    // Ry(yaw) * Rx(pitch) takes -Z to (-cos(pitch) sin(yaw), sin(pitch), -cos(pitch) cos(yaw)).
    out_rotation_deg[0] = asinf(glm_clamp(d[1], -1.0f, 1.0f)) * RAD_TO_DEG;
    out_rotation_deg[1] = atan2f(-d[0], -d[2]) * RAD_TO_DEG;
    out_rotation_deg[2] = 0.0f;
    return true;
}
