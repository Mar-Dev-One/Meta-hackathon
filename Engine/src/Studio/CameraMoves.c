// camera.move: a shot's camera as timeline keys, from a named move and a few
// numbers -- so an agent asks for "orbit the product 60 degrees over 4
// seconds" instead of working out camera positions.
//
// Every move writes three tracks over [start, start + duration): the
// camera's position, its look-at target's position ("<camera>_target", which
// the studio keeps the camera aimed at), and its field of view. Keys already
// in that range are replaced, so each move fully defines its shot, and a
// move that starts where another ends is a cut: the last key sits just
// before the end (MOVE_END_GAP), the next move's first key at its start.
//
// Framing: the subject's bounding sphere fills `fill` of the frame's
// smaller dimension (0.6 by default), seen from `azimuth` degrees around it
// (0 = from the front, +Z; 90 = from its right, +X) and `elevation` degrees
// above it.

#include "CameraMoves.h"

#include "Common/Json.h"
#include "Studio.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#define DEG_TO_RAD (3.14159265358979f / 180.0f)

// Curved moves (orbit, crane) are sampled into keys this many seconds apart;
// a straight line between neighbours is then within a millimetre of the arc.
#define MOVE_SAMPLE_SPACING 0.1f

// A move's last key is this long before its end, so the next move's first
// key can start a new shot at exactly the end time.
#define MOVE_END_GAP 0.001f

typedef enum move_kind
{
    MOVE_STATIC,   // holds a framing
    MOVE_ORBIT,    // around the subject, azimuth -> to_azimuth
    MOVE_DOLLY,    // towards or away from it along the view line, from_fill -> to_fill
    MOVE_CRANE,    // over or under it on an arc, from_elevation -> to_elevation
    MOVE_TRUCK,    // sideways, past it: camera and aim travel together
    MOVE_REVEAL,   // the camera holds while the aim pans onto the subject from off it
    MOVE_ZOOM,     // the lens alone: from_fov -> to_fov
    MOVE_COUNT
} move_kind;

static const char* const MOVE_NAMES[MOVE_COUNT] = { "static", "orbit", "dolly", "crane", "truck", "reveal", "zoom" };
static const char* const REVEAL_NAMES[4]        = { "above", "below", "left", "right" };

typedef struct move
{
    move_kind     kind;
    f32           start, duration;
    timeline_ease ease;

    vec3 center;   // the subject's bounding sphere
    f32  radius;

    f32 fov, fill, azimuth, elevation, aspect;
    f32 to_azimuth, from_fill, to_fill, from_elevation, to_elevation, travel, from_fov, to_fov;
    int reveal_from;   // REVEAL_NAMES' index
} move;

// How far from the subject's centre its bounding sphere fills `fill` of the
// frame's smaller dimension.
static f32
framing_distance(const move* m, f32 fill, f32 fov)
{
    f32 tan_v = tanf(0.5f * fov * DEG_TO_RAD);
    f32 tan_h = tan_v * m->aspect;
    return m->radius / (fill * fminf(tan_v, tan_h));
}

// A point `distance` from `center`, `azimuth` degrees around and `elevation` degrees up.
static void
around(const vec3 center, f32 distance, f32 azimuth, f32 elevation, vec3 out)
{
    f32 az = azimuth * DEG_TO_RAD, el = elevation * DEG_TO_RAD;
    out[0] = center[0] + distance * sinf(az) * cosf(el);
    out[1] = center[1] + distance * sinf(el);
    out[2] = center[2] + distance * cosf(az) * cosf(el);
}

// The camera's position, aim and lens at progress u (0..1, already eased for sampled moves).
static void
pose(const move* m, f32 u, vec3 position, vec3 target, f32* fov)
{
    f32 az = m->azimuth, el = m->elevation, fill = m->fill;
    *fov = m->fov;
    glm_vec3_copy((f32*)m->center, target);

    switch (m->kind)
    {
        case MOVE_ORBIT: az   = glm_lerp(m->azimuth, m->to_azimuth, u); break;
        case MOVE_DOLLY: fill = glm_lerp(m->from_fill, m->to_fill, u); break;
        case MOVE_CRANE: el   = glm_lerp(m->from_elevation, m->to_elevation, u); break;
        case MOVE_ZOOM:  *fov = glm_lerp(m->from_fov, m->to_fov, u); break;
        default: break;
    }
    // A zoom keeps the camera where the end lens frames the subject.
    around(m->center, framing_distance(m, fill, m->kind == MOVE_ZOOM ? m->to_fov : *fov), az, el, position);

    if (m->kind == MOVE_TRUCK)
    {
        // Sideways: the horizontal direction to the camera's right.
        vec3 right  = { cosf(az * DEG_TO_RAD), 0.0f, -sinf(az * DEG_TO_RAD) };
        f32  offset = glm_lerp(-0.5f * m->travel, 0.5f * m->travel, u);
        glm_vec3_muladds(right, offset, position);
        glm_vec3_muladds(right, offset, target);
    }
    else if (m->kind == MOVE_REVEAL)
    {
        // The aim starts three radii off the subject and comes onto it.
        vec3 right = { cosf(az * DEG_TO_RAD), 0.0f, -sinf(az * DEG_TO_RAD) };
        vec3 off[4] = { { 0.0f, 1.0f, 0.0f }, { 0.0f, -1.0f, 0.0f }, { -right[0], 0.0f, -right[2] }, { right[0], 0.0f, right[2] } };
        glm_vec3_muladds(off[m->reveal_from], 3.0f * m->radius * (1.0f - u), target);
    }
}

// --- Writing the keys -------------------------------------------------------------------

typedef struct move_tracks
{
    const char* camera;
    const char* target;
    uint32      keys;
} move_tracks;

static b8
add_pose_keys(studio* s, move_tracks* tracks, f32 t, f32 u, timeline_ease ease, const move* m,
              char* error, size_t error_size)
{
    vec3 position, target;
    f32  fov;
    pose(m, u, position, target, &fov);

    timeline_key key = { .time = t, .ease = ease };
    glm_vec3_copy(position, key.value);
    if (!timeline_add_key(&s->timeline, tracks->camera, "Transform", "position", &key, error, error_size))
        return false;
    glm_vec3_copy(target, key.value);
    if (!timeline_add_key(&s->timeline, tracks->target, "Transform", "position", &key, error, error_size))
        return false;
    key.value[0] = fov;
    if (!timeline_add_key(&s->timeline, tracks->camera, "Camera", "fov_degrees", &key, error, error_size))
        return false;
    tracks->keys += 3;
    return true;
}

static b8
write_move(studio* s, move_tracks* tracks, const move* m, char* error, size_t error_size)
{
    f32 end = m->start + m->duration;
    timeline_remove_keys(&s->timeline, tracks->camera, "Transform", "position", m->start, end);
    timeline_remove_keys(&s->timeline, tracks->target, "Transform", "position", m->start, end);
    timeline_remove_keys(&s->timeline, tracks->camera, "Camera", "fov_degrees", m->start, end);

    f32 last = end - fminf(MOVE_END_GAP, 0.5f * m->duration);
    if (m->kind == MOVE_ORBIT || m->kind == MOVE_CRANE)
    {
        // Curved: samples along the eased path, joined by straight lines.
        uint32 segments = (uint32)ceilf(m->duration / MOVE_SAMPLE_SPACING);
        for (uint32 i = 0; i <= segments; ++i)
        {
            f32 u = (f32)i / (f32)segments;
            if (!add_pose_keys(s, tracks, glm_lerp(m->start, last, u), timeline_ease_apply(m->ease, NULL, u),
                               EASE_LINEAR, m, error, error_size))
                return false;
        }
        return true;
    }
    // Straight: two keys, the timeline eases between them.
    return add_pose_keys(s, tracks, m->start, 0.0f, m->ease, m, error, error_size)
           && add_pose_keys(s, tracks, last, 1.0f, EASE_LINEAR, m, error, error_size);
}

// --- camera.move --------------------------------------------------------------------------

static b8
read_name(const cJSON* args, const char* key, const char* const* names, int count, int fallback, int* out,
          char* error, size_t error_size)
{
    const char* value = NULL;
    if (arg_string(args, key, &value, error, error_size) < 0)
        return false;
    *out = fallback;
    if (!value)
        return true;
    for (int i = 0; i < count; ++i)
    {
        if (strcmp(value, names[i]) == 0)
        {
            *out = i;
            return true;
        }
    }
    char list[256] = "";
    for (int i = 0; i < count; ++i)
        snprintf(list + strlen(list), sizeof(list) - strlen(list), "%s\"%s\"", i ? ", " : "", names[i]);
    return set_error(error, error_size, "\"%s\" must be one of %s", key, list);
}

static b8
cmd_camera_move(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio* s = (studio*)user;
    move    m = { .fov = STUDIO_DEFAULT_FOV, .fill = 0.6f, .elevation = 10.0f, .aspect = 16.0f / 9.0f, .ease = EASE_IN_OUT };

    int kind;
    if (!cJSON_GetObjectItemCaseSensitive(args, "move"))
        return set_error(error, error_size, "\"move\" must be given: static, orbit, dolly, crane, truck, reveal or zoom");
    if (!read_name(args, "move", MOVE_NAMES, MOVE_COUNT, 0, &kind, error, error_size))
        return false;
    m.kind = (move_kind)kind;

    const char* subject     = NULL;
    const char* camera_name = s->active_camera[0] ? s->active_camera : STUDIO_DEFAULT_CAMERA;
    const char* ease        = NULL;
    if (arg_string(args, "subject", &subject, error, error_size) <= 0)
        return set_error(error, error_size, "\"subject\" must name the entity to frame (one with a MeshRenderer)");
    if (arg_string(args, "camera", &camera_name, error, error_size) < 0 || arg_string(args, "ease", &ease, error, error_size) < 0)
        return false;
    if (strlen(camera_name) >= ENTITY_NAME_MAX)
        return set_error(error, error_size, "\"camera\" is at most %d characters", ENTITY_NAME_MAX - 1);
    char camera[ENTITY_NAME_MAX];   // a copy: the name may be s->active_camera itself, which is written below
    snprintf(camera, sizeof(camera), "%s", camera_name);
    if (ease && (!timeline_ease_from_name(ease, &m.ease) || m.ease == EASE_STEP || m.ease == EASE_BEZIER))
        return set_error(error, error_size, "\"ease\" must be \"linear\", \"in\", \"out\" or \"in_out\"");

    // The common numbers, then each move's own, defaulting from the common ones.
    int has_duration = arg_number(args, "duration", 0.05f, 600.0f, &m.duration, error, error_size);
    if (has_duration < 0)
        return false;
    if (has_duration == 0)
        return set_error(error, error_size, "\"duration\" must be given: seconds, 0.05 to 600");
    if (arg_number(args, "start", 0.0f, 3600.0f, &m.start, error, error_size) < 0
        || arg_number(args, "fov_degrees", 1.0f, 179.0f, &m.fov, error, error_size) < 0
        || arg_number(args, "fill", 0.05f, 5.0f, &m.fill, error, error_size) < 0
        || arg_number(args, "azimuth", -3600.0f, 3600.0f, &m.azimuth, error, error_size) < 0
        || arg_number(args, "elevation", -85.0f, 85.0f, &m.elevation, error, error_size) < 0
        || arg_number(args, "aspect", 0.2f, 5.0f, &m.aspect, error, error_size) < 0)
        return false;

    m.to_azimuth     = m.azimuth + 60.0f;
    m.from_fill      = m.fill * 0.6f;
    m.to_fill        = m.fill;
    m.from_elevation = m.elevation - 15.0f;
    m.to_elevation   = m.elevation + 25.0f;
    m.from_fov       = fminf(m.fov * 1.5f, 120.0f);
    m.to_fov         = m.fov;
    if (arg_number(args, "to_azimuth", -3600.0f, 3600.0f, &m.to_azimuth, error, error_size) < 0
        || arg_number(args, "from_fill", 0.05f, 5.0f, &m.from_fill, error, error_size) < 0
        || arg_number(args, "to_fill", 0.05f, 5.0f, &m.to_fill, error, error_size) < 0
        || arg_number(args, "from_elevation", -85.0f, 85.0f, &m.from_elevation, error, error_size) < 0
        || arg_number(args, "to_elevation", -85.0f, 85.0f, &m.to_elevation, error, error_size) < 0
        || arg_number(args, "from_fov", 1.0f, 179.0f, &m.from_fov, error, error_size) < 0
        || arg_number(args, "to_fov", 1.0f, 179.0f, &m.to_fov, error, error_size) < 0
        || arg_number(args, "travel", -100.0f, 100.0f, &m.travel, error, error_size) < 0
        || !read_name(args, "from", REVEAL_NAMES, 4, 0, &m.reveal_from, error, error_size))
        return false;
    m.from_elevation = glm_clamp(m.from_elevation, -85.0f, 85.0f);
    m.to_elevation   = glm_clamp(m.to_elevation, -85.0f, 85.0f);

    char target[ENTITY_NAME_MAX];
    if (snprintf(target, sizeof(target), "%s_target", camera) >= (int)sizeof(target))
        return set_error(error, error_size, "\"camera\" is too long a name for its \"_target\"");

    // The subject's size at the move's start (it may itself be animated).
    f32 previous = s->timeline.time;
    studio_evaluate(s, m.start, NULL);
    entity_id subject_entity = world_find(s->w, subject);
    vec3      lo, hi;
    if (!subject_entity || !world_bounds(s->w, subject_entity, lo, hi))
    {
        studio_evaluate(s, previous, NULL);
        return set_error(error, error_size, "\"%s\" isn't an entity with a MeshRenderer and a model", subject);
    }
    glm_vec3_center(lo, hi, m.center);
    m.radius = fmaxf(0.5f * glm_vec3_distance(lo, hi), 1e-3f);
    if (!cJSON_GetObjectItemCaseSensitive(args, "travel"))
        m.travel = 2.0f * m.radius;

    // The camera and its target, then the keys.
    studio_camera_entity(s, camera);
    if (!world_find(s->w, target))
        world_create(s->w, target);
    move_tracks tracks = { .camera = camera, .target = target };
    b8 ok = write_move(s, &tracks, &m, error, error_size);
    if (ok)
    {
        snprintf(s->active_camera, sizeof(s->active_camera), "%s", camera);
        snprintf(s->look_at, sizeof(s->look_at), "%s", target);
    }
    studio_evaluate(s, previous, NULL);
    if (!ok)
        return false;

    *out_result = cJSON_CreateObject();
    cJSON_AddStringToObject(*out_result, "move", MOVE_NAMES[m.kind]);
    cJSON_AddStringToObject(*out_result, "camera", camera);
    cJSON_AddStringToObject(*out_result, "look_at", target);
    cJSON_AddNumberToObject(*out_result, "start", json_round6(m.start));
    cJSON_AddNumberToObject(*out_result, "end", json_round6(m.start + m.duration));
    cJSON_AddNumberToObject(*out_result, "keys", tracks.keys);
    cJSON_AddNumberToObject(*out_result, "subject_radius", json_round6(m.radius));
    cJSON_AddNumberToObject(*out_result, "distance", json_round6(framing_distance(&m, m.kind == MOVE_DOLLY ? m.from_fill : m.fill,
                                                                                   m.kind == MOVE_ZOOM ? m.to_fov : m.fov)));
    return true;
}

// --- Table ----------------------------------------------------------------------------

static const cmd_arg MOVE_ARGS[] = {
    { "move", "string", true, "static, orbit, dolly, crane, truck (sideways past), reveal (aim pans onto it) or zoom" },
    { "subject", "string", true, "the entity to frame, e.g. the product" },
    { "duration", "number", true, "seconds" },
    { "start", "number", false, "seconds (default 0); keys already in [start, start + duration) are replaced" },
    { "ease", "string", false, "linear, in, out or in_out (default)" },
    { "camera", "string", false, "the Camera entity (default the active one, or \"camera\"); created if missing" },
    { "fill", "number", false, "how much of the frame's height the subject fills, 0.05 to 5 (default 0.6)" },
    { "azimuth", "number", false, "degrees around the subject: 0 = front (+Z), 90 = its right (+X) (default 0)" },
    { "elevation", "number", false, "degrees above the subject, -85 to 85 (default 10)" },
    { "fov_degrees", "number", false, "vertical field of view (default 30)" },
    { "aspect", "number", false, "the frame's width / height, for framing (default 16/9)" },
    { "to_azimuth", "number", false, "orbit: where it ends (default azimuth + 60)" },
    { "from_fill", "number", false, "dolly: the framing it starts from (default fill * 0.6: pushes in)" },
    { "to_fill", "number", false, "dolly: the framing it ends on (default fill)" },
    { "from_elevation", "number", false, "crane: start (default elevation - 15)" },
    { "to_elevation", "number", false, "crane: end (default elevation + 25)" },
    { "travel", "number", false, "truck: meters moved to the right, negative for left (default the subject's width)" },
    { "from", "string", false, "reveal: where the aim starts, above (default), below, left or right" },
    { "from_fov", "number", false, "zoom: start lens (default fov_degrees * 1.5)" },
    { "to_fov", "number", false, "zoom: end lens (default fov_degrees)" },
};

static const cmd_host_command CAMERA_MOVE_COMMANDS[] = {
    { "camera.move", "Writes a shot's camera move as keys: the camera keeps the subject framed and aimed at it. "
                     "Each move replaces the keys in its own time range, so moves placed end to end are cuts.",
      MOVE_ARGS, sizeof(MOVE_ARGS) / sizeof(MOVE_ARGS[0]), true, cmd_camera_move },
};

const cmd_host_command*
camera_move_commands(uint32* out_count)
{
    *out_count = sizeof(CAMERA_MOVE_COMMANDS) / sizeof(CAMERA_MOVE_COMMANDS[0]);
    return CAMERA_MOVE_COMMANDS;
}
