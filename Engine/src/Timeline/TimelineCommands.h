#pragma once

#include "Commands/Commands.h"

// The timeline's commands, run on a studio's timeline (host_user = the
// studio; Studio/Studio.h lists them). studio_commands() includes them.
const cmd_host_command* timeline_commands(uint32* out_count);
