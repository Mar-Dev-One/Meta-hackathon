# Fonts

Open-licensed fonts the Studio draws titles with. Each is under the SIL Open Font License 1.1; its licence is next to it (`*-OFL.txt`). Copied to `<exe>/assets/fonts` at build time.

| Style | File | Font | Source |
|---|---|---|---|
| `serif`: luxury, editorial | `PlayfairDisplay.ttf` | Playfair Display (variable; drawn at its default, Regular) | [google/fonts](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) |
| `sans`: clean, modern | `Montserrat-Regular.ttf` | Montserrat Regular | [JulietaUla/Montserrat](https://github.com/JulietaUla/Montserrat) |
| `sans_bold`: strong headlines | `Montserrat-SemiBold.ttf` | Montserrat SemiBold | [JulietaUla/Montserrat](https://github.com/JulietaUla/Montserrat) |
| `condensed`: bold, sporty, energetic | `Oswald.ttf` | Oswald (variable; drawn at its default, Regular) | [google/fonts](https://github.com/google/fonts/tree/main/ofl/oswald) |
| `script`: handwritten, elegant | `GreatVibes-Regular.ttf` | Great Vibes | [google/fonts](https://github.com/google/fonts/tree/main/ofl/greatvibes) |

Kerning: these fonts keep their kerning in OpenType GPOS lookups that `stb_truetype` doesn't read, so pairs like "AV" and "To" aren't pulled together yet (docs/ROADMAP.md, step 1.7a+).
