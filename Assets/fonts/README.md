# Fonts

Open-licensed fonts the Studio draws titles with. Each is under the SIL Open Font License 1.1; its licence is next to it (`*-OFL.txt`). Copied to `<exe>/assets/fonts` at build time.

| Style | File | Font | Source |
|---|---|---|---|
| `serif`: luxury, editorial | `PlayfairDisplay.ttf` | Playfair Display (variable; drawn at its default, Regular) | [google/fonts](https://github.com/google/fonts/tree/main/ofl/playfairdisplay) |
| `sans`: clean, modern | `Montserrat-Regular.ttf` | Montserrat Regular | [JulietaUla/Montserrat](https://github.com/JulietaUla/Montserrat) |
| `sans_bold`: strong headlines | `Montserrat-SemiBold.ttf` | Montserrat SemiBold | [JulietaUla/Montserrat](https://github.com/JulietaUla/Montserrat) |
| `condensed`: bold, sporty, energetic | `Oswald.ttf` | Oswald (variable; drawn at its default, Regular) | [google/fonts](https://github.com/google/fonts/tree/main/ofl/oswald) |
| `script`: handwritten, elegant | `GreatVibes-Regular.ttf` | Great Vibes | [google/fonts](https://github.com/google/fonts/tree/main/ofl/greatvibes) |

## Kerning

These fonts keep their kerning (how much closer pairs like "AV", "To", "Wa" sit) in OpenType GPOS lookups that `stb_truetype` doesn't read. `scripts/font_kerning.py` reads them with fontTools and writes `<font>.kern.json` beside each font; the Studio loads that with the font. After adding or replacing a font:

```
.venv\Scripts\python scripts\font_kerning.py Assets\fonts\*.ttf
```
