# Meta_Engine: the studio built on PBR_Engine during the hackathon -- the
# commands an agent sets up a shot with, and (docs/ROADMAP.md, Phase 1) the
# timeline, text, products and shot rendering that follow.
#
# It uses the engine only through its installed headers and library; the
# engine itself is not changed.

add_library(Meta_Engine STATIC
    src/Common/Json.c
    src/Shot/Shot.c
    src/Shot/ShotCommands.c
    src/Studio/CameraMoves.c
    src/Studio/Studio.c
    src/Studio/StudioCommands.c
    src/Timeline/Timeline.c
    src/Timeline/TimelineCommands.c
)
target_include_directories(Meta_Engine PUBLIC src)
target_link_libraries(Meta_Engine PUBLIC PBR_Engine)

# --- Tests: ctest --test-dir build -C Release ---------------------------------

add_executable(Timeline_Tests tests/timeline_tests.c)
target_link_libraries(Timeline_Tests PRIVATE Meta_Engine)
add_test(NAME timeline COMMAND Timeline_Tests)
