cmake_minimum_required(VERSION 3.26)

# The Studio: the renderer the agents drive over the command server, built on
# the engine's PBR_Engine and on Meta_Engine (Engine/, written here).
#
# The engine comes prebuilt in Deps/ (headers in Deps/Includes/PBR, MSVC
# Release libraries in Deps/Libs), so this needs MSVC:
#
#   cmake -S . -B build
#   cmake --build build --config Release
project(Meta_Hackathon LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT MSVC)
    message(FATAL_ERROR "Deps/Libs holds MSVC libraries; configure with a Visual Studio generator or from a VS developer prompt")
endif()

# The libraries were built Release against the DLL C runtime (/MD). Debug's
# /MDd can't be mixed with them, so every configuration uses /MD: a Debug
# build is our code unoptimized with symbols, on the release runtime.
set(CMAKE_MSVC_RUNTIME_LIBRARY MultiThreadedDLL)
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(OpenGL REQUIRED)

# --- PBR_Engine (prebuilt) ----------------------------------------------------

set(DEPS_DIR ${CMAKE_CURRENT_SOURCE_DIR}/Deps)

add_library(PBR_Engine INTERFACE)
target_include_directories(PBR_Engine INTERFACE ${DEPS_DIR}/Includes/PBR)
target_link_libraries(PBR_Engine INTERFACE
    ${DEPS_DIR}/Libs/PBR_Engine.lib
    ${DEPS_DIR}/Libs/cimgui.lib
    ${DEPS_DIR}/Libs/glfw3.lib
    ${DEPS_DIR}/Libs/glad.lib
    OpenGL::GL
    ws2_32
)

# --- Meta_Engine (built here) -------------------------------------------------

add_subdirectory(Engine)

# --- Studio -------------------------------------------------------------------

add_executable(Studio src/main.c)
target_link_libraries(Studio PRIVATE Meta_Engine)

# Everything the program loads at runtime goes in assets/ next to it, so the
# build folder runs on its own and can be copied elsewhere:
#   assets/shaders          the engine's root (Core/Paths.h)
#   assets/models, /hdri    the project root; main.c sets it
add_custom_command(TARGET Studio POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/Assets/Shaders/shaders
            $<TARGET_FILE_DIR:Studio>/assets/shaders
    COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/Assets/models
            $<TARGET_FILE_DIR:Studio>/assets/models
    COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different
            ${CMAKE_CURRENT_SOURCE_DIR}/Assets/hdri
            $<TARGET_FILE_DIR:Studio>/assets/hdri
)

# vcruntime140.dll goes next to the program too: Windows 10/11 ship the rest
# of the C runtime (the UCRT), but not this, so a PC without the Visual C++
# Redistributable couldn't start it. InstallRequiredSystemLibraries finds it
# in the compiler's redist folder; the program needs no other DLL from there.
set(CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS_SKIP TRUE)
include(InstallRequiredSystemLibraries)
list(FILTER CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS INCLUDE REGEX "/vcruntime140\\.dll$")
if(NOT CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS)
    message(FATAL_ERROR "vcruntime140.dll not found in the MSVC redist folder")
endif()
add_custom_command(TARGET Studio POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
            ${CMAKE_INSTALL_SYSTEM_RUNTIME_LIBS}
            $<TARGET_FILE_DIR:Studio>
)

set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT Studio)
