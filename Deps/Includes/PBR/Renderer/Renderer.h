#pragma once

#include "../Core/Defines.h"

#include "../Platform/Window.h"

typedef struct renderer
{
    window* drawing_window;
}*renderer;

b8 init_renderer(window_descriptor init_window_desc);

renderer get_renderer();

void renderer_begin_frame();
void renderer_end_frame();

void renderer_set_viewport(uint16 x, uint16 y, uint16 width, uint16 height);

void renderer_clear(f32 r, f32 g, f32 b, f32 a);

void terminate_renderer();
