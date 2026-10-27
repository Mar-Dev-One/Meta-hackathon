#pragma once

#include "Commands/Commands.h"

// The shot commands, run on a studio (host_user = the studio; Studio/Studio.h
// lists them). studio_commands() includes them.
const cmd_host_command* shot_commands(uint32* out_count);
