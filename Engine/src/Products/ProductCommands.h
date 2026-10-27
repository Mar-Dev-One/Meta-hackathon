#pragma once

#include "Commands/Commands.h"

// product.create and backdrop.create, run on a studio (host_user = the
// studio; Studio/Studio.h lists them). studio_commands() includes them.
const cmd_host_command* product_commands(uint32* out_count);
