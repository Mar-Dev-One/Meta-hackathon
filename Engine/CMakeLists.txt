# Meta_Engine: the studio built on PBR_Engine during the hackathon -- the
# commands an agent sets up a shot with, and (docs/ROADMAP.md, Phase 1) the
# timeline, text, products and shot rendering that follow.
#
# It uses the engine only through its installed headers and library; the
# engine itself is not changed.

add_library(Meta_Engine STATIC
    src/Common/Json.c
    src/Products/Geometry.c
    src/Products/Products.c
    src/Shot/Shot.c
    src/Shot/ShotCommands.c
    src/Studio/CameraMoves.c
    src/Studio/Lighting.c
    src/Studio/Studio.c
    src/Studio/StudioCommands.c
    src/Text/Font.c
    src/Timeline/Timeline.c
    src/Timeline/TimelineCommands.c
)
target_include_directories(Meta_Engine PUBLIC src PRIVATE deps)   # deps: stb_truetype, private to Text/Font.c
target_link_libraries(Meta_Engine PUBLIC PBR_Engine)

# --- Tests: ctest --test-dir build -C Release ---------------------------------

add_executable(Timeline_Tests tests/timeline_tests.c)
target_link_libraries(Timeline_Tests PRIVATE Meta_Engine)
add_test(NAME timeline COMMAND Timeline_Tests)

# Loads the fonts from Assets/fonts; writes atlases and sample text to look at.
add_executable(Text_Tests tests/text_tests.c)
target_link_libraries(Text_Tests PRIVATE Meta_Engine)
target_compile_definitions(Text_Tests PRIVATE
    FONT_DIR="${PROJECT_SOURCE_DIR}/Assets/fonts"
    OUT_DIR="${CMAKE_CURRENT_BINARY_DIR}/text_test_out")
file(MAKE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/text_test_out)
add_test(NAME text COMMAND Text_Tests)
