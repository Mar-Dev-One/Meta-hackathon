// The text commands (Studio.h lists them), run on the studio's text layer.

#include "TextCommands.h"

#include "Common/Json.h"
#include "Studio/Studio.h"
#include "Text.h"

#include <string.h>

static b8
read_name(const cJSON* args, const char** name, char* error, size_t error_size)
{
    if (arg_string(args, "name", name, error, error_size) <= 0)
        return set_error(error, error_size, "\"name\" must name the text, e.g. \"title\"");
    if (strlen(*name) >= ENTITY_NAME_MAX)
        return set_error(error, error_size, "\"name\" is at most %d characters", ENTITY_NAME_MAX - 1);
    return true;
}

// The item and where it lands in a 16:9 frame, as shares of that frame's
// width and height: left, top, width, height.
static cJSON*
describe(studio* s, const text_item* item)
{
    cJSON* json = text_item_to_json(item);
    f32    box[4];
    if (text_measure(&s->texts, item, 1920.0f, 1080.0f, box))
    {
        f32 shares[4] = { box[0] / 1920.0f, box[1] / 1080.0f, box[2] / 1920.0f, box[3] / 1080.0f };
        json_add_floats(json, "box", shares, 4);
    }
    return json;
}

static b8
cmd_create(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s = (studio*)user;
    const char* name;
    if (!read_name(args, &name, error, error_size))
        return false;
    if (text_find(&s->texts, name))
        return set_error(error, error_size, "there's already a text \"%s\": change it with text.set", name);

    if (s->texts.count == TEXT_MAX_ITEMS)
        return set_error(error, error_size, "there are already %d texts: remove one first", TEXT_MAX_ITEMS);
    text_item draft;
    text_item_defaults(&draft, name);
    if (!text_item_from_json(&s->texts, &draft, args, false, error, error_size))
        return false;

    text_item* item = text_add(&s->texts, name);
    *item           = draft;
    *out_result     = describe(s, item);
    return true;
}

static b8
cmd_set(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s = (studio*)user;
    const char* name;
    if (!read_name(args, &name, error, error_size))
        return false;
    text_item* item = text_find(&s->texts, name);
    if (!item)
        return set_error(error, error_size, "there's no text \"%s\": make it with text.create", name);
    if (!text_item_from_json(&s->texts, item, args, false, error, error_size))
        return false;
    *out_result = describe(s, item);
    return true;
}

static b8
cmd_remove(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)out_result;
    studio*     s = (studio*)user;
    const char* name;
    if (!read_name(args, &name, error, error_size))
        return false;
    return text_remove(&s->texts, name) || set_error(error, error_size, "there's no text \"%s\"", name);
}

// Where a title would land in a width x height frame, without adding it:
// an existing one (by name) with any fields changed, or a new one.
static b8
cmd_measure(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx;
    studio*     s    = (studio*)user;
    const char* name = NULL;
    f32         width = 1920.0f, height = 1080.0f;
    if (arg_string(args, "name", &name, error, error_size) < 0
        || arg_number(args, "width", 16.0f, 8192.0f, &width, error, error_size) < 0
        || arg_number(args, "height", 16.0f, 8192.0f, &height, error, error_size) < 0)
        return false;

    text_item  draft;
    text_item* existing = name ? text_find(&s->texts, name) : NULL;
    if (existing)
        draft = *existing;
    else
        text_item_defaults(&draft, "measure");
    if (!text_item_from_json(&s->texts, &draft, args, false, error, error_size))
        return false;
    if (!draft.text[0])
        return set_error(error, error_size, "there's no \"text\" to measure");

    f32 box[4];
    if (!text_measure(&s->texts, &draft, width, height, box))
        return set_error(error, error_size, "the %s font didn't load", draft.font);
    f32 shares[4] = { box[0] / width, box[1] / height, box[2] / width, box[3] / height };
    *out_result = cJSON_CreateObject();
    json_add_floats(*out_result, "box_px", box, 4);
    json_add_floats(*out_result, "box", shares, 4);
    cJSON_AddBoolToObject(*out_result, "fits", box[0] >= 0.0f && box[1] >= 0.0f && box[0] + box[2] <= width
                                                   && box[1] + box[3] <= height);
    return true;
}

static b8
cmd_get(void* user, command_context* ctx, const cJSON* args, cJSON** out_result, char* error, size_t error_size)
{
    (void)ctx; (void)args; (void)error; (void)error_size;
    studio* s = (studio*)user;
    *out_result  = cJSON_CreateObject();
    cJSON* texts = cJSON_AddArrayToObject(*out_result, "texts");
    for (uint32 i = 0; i < s->texts.count; ++i)
        cJSON_AddItemToArray(texts, describe(s, &s->texts.items[i]));
    return true;
}

// --- Table ----------------------------------------------------------------------------

#define TEXT_FIELD_ARGS                                                                                                  \
    { "text", "string", false, "UTF-8; \\n starts a new line" },                                                        \
    { "font", "string", false, "serif (luxury), sans (clean), sans_bold, condensed (bold, sporty) or script (default sans)" }, \
    { "size", "number", false, "the font's em as a share of the frame's height, 0.005 to 1 (default 0.06)" },             \
    { "anchor", "string", false, "top_left, top, top_right, left, center (default), right, bottom_left, bottom, "        \
                                 "bottom_right: the frame point it hangs from, and how lines align" },                   \
    { "offset", "array", false, "[x, y] from the anchor in shares of the frame, +y down, e.g. [0, -0.08]" },             \
    { "color", "string", false, "\"#RRGGBB\" or \"#RRGGBBAA\", as seen (default white)" },                               \
    { "opacity", "number", false, "0 to 1" },                                                                             \
    { "tracking", "number", false, "extra space between letters in ems, e.g. 0.2 for wide luxury caps" },                \
    { "scale", "number", false, "times size (for animating)" },                                                          \
    { "line_spacing", "number", false, "times the font's line height (default 1)" },                                     \
    { "visible", "boolean", false, "draw it (default true)" }

static const cmd_arg CREATE_ARGS[] = {
    { "name", "string", true, "the text's name, e.g. \"title\"" },
    TEXT_FIELD_ARGS,
};

static const cmd_arg SET_ARGS[] = {
    { "name", "string", true, "the text to change" },
    TEXT_FIELD_ARGS,
};

static const cmd_arg REMOVE_ARGS[] = {
    { "name", "string", true, "the text to remove" },
};

static const cmd_arg MEASURE_ARGS[] = {
    { "name", "string", false, "an existing text to start from (the other fields change it, for this measurement only)" },
    { "width", "number", false, "the frame's width in pixels (default 1920)" },
    { "height", "number", false, "the frame's height in pixels (default 1080)" },
    TEXT_FIELD_ARGS,
};

#define COUNT_OF(a) (uint32)(sizeof(a) / sizeof((a)[0]))

static const cmd_host_command TEXT_COMMANDS[] = {
    { "text.create", "Adds a title drawn over the picture, in every frame and shot. Its box in the result is in "
                     "shares of the frame: left, top, width, height.",
      CREATE_ARGS, COUNT_OF(CREATE_ARGS), false, cmd_create },
    { "text.set", "Changes any of a title's fields; the others keep their values.",
      SET_ARGS, COUNT_OF(SET_ARGS), false, cmd_set },
    { "text.remove", "Removes a title.", REMOVE_ARGS, COUNT_OF(REMOVE_ARGS), false, cmd_remove },
    { "text.get", "Every title, with its box in shares of the frame.", NULL, 0, false, cmd_get },
    { "text.measure", "Where a title would land in a frame, without adding it: its box in pixels and in shares "
                      "of the frame, and whether it fits inside.",
      MEASURE_ARGS, COUNT_OF(MEASURE_ARGS), false, cmd_measure },
};

const cmd_host_command*
text_commands(uint32* out_count)
{
    *out_count = COUNT_OF(TEXT_COMMANDS);
    return TEXT_COMMANDS;
}
