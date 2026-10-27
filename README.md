# Meta-hackathon

A testbed that builds a PBR scene in code with the prebuilt `PBR_Engine` library and draws it.

## Build

Requires Windows, Visual Studio 2022 (MSVC) and CMake 3.26+. The engine libraries in `Deps/Libs` are MSVC Release builds, so every configuration links the release C runtime (`/MD`). A Debug build is your code unoptimized with symbols. The engine itself stays optimized.

```
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
build\Release\Testbed.exe
```

`Testbed.exe --check out.png` renders the scene in a hidden window, saves it and exits (0 on success). `--view NAME` shows a debug view (albedo, normals, roughness, metallic, ao, shadow, lighting, wireframe, lights).

## Layout

- `src/main.c` builds the scene and runs it
- `Deps/` holds the engine headers (`Includes/PBR`) and prebuilt libraries (`Libs`)
- `Assets/Shaders/shaders` holds the engine's shaders. They are copied to `<exe>/assets/shaders` at build time
- `Assets/models` and `Assets/hdri` hold the models and HDRI the scene loads. They are copied to `<exe>/assets` at build time

At runtime the program loads everything from the `assets/` folder next to it. `PBR_Engine.lib` was built with no absolute paths, so nothing outside the build folder is used. You can copy `build/Release` to another machine and run it there. The build also copies `vcruntime140.dll` next to the exe, so a Windows 10/11 PC without Visual Studio or the Visual C++ Redistributable can run it. It only needs an OpenGL 4.x graphics driver.
