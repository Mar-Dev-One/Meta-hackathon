#pragma once

#include "Defines.h"

// Where files are found at runtime. Two roots, chosen when the program runs
// rather than baked in at compile time, so a copied or exported build still
// finds its files:
//
//   engine root   the engine's own data: shaders/. The first that has
//                 shaders/pbr.vert of
//                   1. <executable's folder>/assets
//                   2. DEV_ENGINE_ROOT
//
//   project root  what a game is made of: scenes/, models/, hdri/,
//                 textures/. Paths stored in scenes ("models/Avocado.glb",
//                 "hdri/sky.hdr") are relative to it.
//                   1. paths_set_project_root() (the apps' --project <dir>)
//                   2. DEV_PROJECT_ROOT
//
// This build of PBR_Engine.lib was compiled with DEV_ENGINE_ROOT and
// DEV_PROJECT_ROOT both "assets" (relative to the working directory), so it
// holds no absolute paths: a program finds everything in the assets/ folder
// next to it.
//
// Roots use '/' separators and have no trailing '/'.

#ifndef DEV_ENGINE_ROOT
#define DEV_ENGINE_ROOT "engine"
#endif
#ifndef DEV_PROJECT_ROOT
#define DEV_PROJECT_ROOT "assets"
#endif

const char* paths_engine_root(void);
const char* paths_project_root(void);

// Makes `directory` (absolute, or relative to the working directory) the
// project root, stored absolute. False, and the root unchanged, if it isn't
// an existing directory.
b8 paths_set_project_root(const char* directory);

// The folder holding the running executable; "" if it can't be found.
const char* paths_executable_dir(void);

// `relative_path` under the engine / project root (e.g. "shaders/pbr.vert",
// "scenes/plaza.json"), heap-allocated. Caller owns the result and must
// free() it.
char* engine_path(const char* relative_path);
char* project_path(const char* relative_path);

// "<home>/.pbr-renderer/<relative_path>" (home: USERPROFILE on Windows, HOME
// elsewhere; "." if unset), creating the .pbr-renderer folder. Per-user
// tool state lives there (recent projects, the live scene file).
// Caller frees.
char* user_data_path(const char* relative_path);
