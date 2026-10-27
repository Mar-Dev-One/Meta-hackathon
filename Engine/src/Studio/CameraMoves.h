#pragma once

#include "Commands/Commands.h"

// camera.move, run on a studio (host_user = the studio; Studio.h lists it).
// studio_commands() includes it.
const cmd_host_command* camera_move_commands(uint32* out_count);
