#pragma once

#include "Commands/Commands.h"

// text.create, text.set, text.remove and text.get, run on a studio's text
// layer (host_user = the studio; Studio/Studio.h lists them).
// studio_commands() includes them.
const cmd_host_command* text_commands(uint32* out_count);
