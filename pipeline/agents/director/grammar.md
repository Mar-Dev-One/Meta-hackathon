# Shot grammar

Written by `python -m pipeline.agents.director.grammar` from the Studio's command descriptions and the Storyboard schema. Don't edit it by hand.

An ad is shots placed end to end; each shot is one camera move over its duration, so each new shot is a cut. The product (shape, materials, label) comes from the brand profile: keep it as it is.

## Camera moves (`shots[].camera`)

Writes a shot's camera move as keys: the camera keeps the subject framed and aimed at it. Each move replaces the keys in its own time range, so moves placed end to end are cuts.

| move | what it does | reads |
|---|---|---|
| `static` | holds still | `fill`, `azimuth`, `elevation`, `fov_degrees` |
| `orbit` | circles the product | `azimuth`, `to_azimuth`, `elevation`, `fill` |
| `dolly` | pushes in or pulls out | `from_fill`, `to_fill`, `azimuth`, `elevation` |
| `crane` | rises or drops round it | `from_elevation`, `to_elevation`, `azimuth`, `fill` |
| `truck` | slides sideways past it | `travel`, `azimuth`, `elevation`, `fill` |
| `reveal` | the aim pans onto it from off frame | `from`, `azimuth`, `elevation`, `fill` |
| `zoom` | the lens zooms, the camera stays | `from_fov`, `to_fov`, `azimuth`, `elevation`, `fill` |

The settings, as the Studio describes them:

- `ease`: linear, in, out or in_out (default)
- `fill`: how much of the frame's height the subject fills, 0.05 to 5 (default 0.6)
- `azimuth`: degrees around the subject: 0 = front (+Z), 90 = its right (+X) (default 0)
- `elevation`: degrees above the subject, -85 to 85 (default 10)
- `fov_degrees`: vertical field of view (default 30)
- `aperture`: depth of field: the f-number, the focus kept on the subject's near side; 0 = everything sharp (default), 2-2.8 a very soft background, 4-5.6 a softened set, 8+ nearly all sharp
- `to_azimuth`: orbit: where it ends (default azimuth + 60)
- `from_fill`: dolly: the framing it starts from (default fill * 0.6: pushes in)
- `to_fill`: dolly: the framing it ends on (default fill)
- `from_elevation`: crane: start (default elevation - 15)
- `to_elevation`: crane: end (default elevation + 25)
- `travel`: truck: meters moved to the right, negative for left (default the subject's width)
- `from`: reveal: where the aim starts, above (default), below, left or right
- `from_fov`: zoom: start lens (default fov_degrees * 1.5)
- `to_fov`: zoom: end lens (default fov_degrees)

## Shots (`shots[]`)

- `id`: s1, s2, ...
- `intent`: what the shot is for, in a sentence: the critic judges it against this
- `duration` (>0.2 .. 30): seconds; shots run back to back from 0

## Light (`look.lighting`)

Presets: three_point, rim_dark (luxury, moody), high_key (clean, bright), top_soft, split (dramatic) or neon_dual (bold).

- `preset` (three_point | rim_dark | high_key | top_soft | split | neon_dual): rim_dark: luxury, moody; high_key: clean, bright (light backdrop); top_soft: natural, skylight; split: dramatic; neon_dual: bold, energetic; three_point: neutral
- `intensity` (0 .. 20, default 1.0): times the preset's brightness
- `turn` (-360 .. 360, default 0.0): degrees to turn the whole setup around the product
- `warmth` (-1 .. 1, default 0.0): -1 cooler .. 1 warmer
- `fade_in` (>0 .. 10): seconds over which every light rises from dark at the start (a reveal)

## The set (`look`)

- `background` (default [0.004, 0.004, 0.006]): linear RGB where nothing is drawn (behind the backdrop's edges)

`look.environment`:

- `use_ibl` (default True): light and reflect with the HDRI
- `show_skybox` (default False): show the HDRI as the background (usually off: the backdrop is the background)
- `ambient_strength` (0 .. 4, default 0.06): 0.05 dark and moody, 0.6 bright and airy
- `exposure` (>0 .. 16, default 1.0)
- `bloom` (0 .. 1, default 0.08): glow around bright highlights; 0.03 clean, 0.14 dreamy or neon
- `tonemap` (agx | aces | neutral, default agx): agx: soft filmic; aces: contrasty; neutral: colours as authored (bright, clean looks)
- `ssao` (default True)

`look.backdrop` (a cyclorama: a floor curving up into a wall):

- `color` (default #0A0A0C): the cyclorama's colour (sRGB)
- `roughness` (0 .. 1, default 0.6)

`look.pedestal` (or null: the product stands on the floor):

- `width` (>0.02 .. 3, default 0.32): diameter, meters; a little wider than the product
- `height` (>0.01 .. 2, default 0.2): meters; the product stands on it
- `color` (default #0E0E10)
- `roughness` (0 .. 1, default 0.85): keep high (0.8+) under rim lights, or its top glares

## Titles (`titles[]`)

Drawn by the Studio over the picture. Fonts: serif (luxury), sans (clean), sans_bold, condensed (bold, sporty) or script (default sans).
Each fades in at `start` while rising a little and its letters drawing together.

- `text`
- `font` (serif | sans | sans_bold | condensed | script): serif: luxury; sans: clean; sans_bold: strong; condensed: bold, sporty; script: elegant, handwritten
- `size` (0.01 .. 0.3): letter height as a share of the frame's height: 0.07 a name, 0.03 a tagline
- `y` (0.05 .. 0.95): vertical centre as a share of the frame's height (0 top); keep clear of the product
- `color`
- `tracking` (-0.2 .. 1.5, default 0.0): extra letter spacing in ems; 0.2-0.3 for wide luxury capitals
- `start`: seconds: when it starts fading in
- `fade` (>0 .. 5, default 0.7): seconds to fade in

## Other animation (`tracks[]`)

Keys on any number field of an entity, eased between. The useful one: the product spinning, `{"entity": "product", "component": "Transform", "field": "rotation_deg", "keys": [{"t": 0, "value": [0, -300, 0], "ease": "out"}, {"t": 6, "value": [0, 0, 0]}]}` (it settles facing front; y is degrees round).

## Ad craft

- Open strong: the product is on screen and readable within the first 2 seconds.
- 3 to 6 shots for 15 seconds; no shot under 1.2 s or over 5 s (the style sets the pace).
- Every shot moves differently from the one before (orbit, then dolly, then crane ...): cuts land on motion.
- Keep the side of the product steady across cuts: don't jump more than about 90 degrees of azimuth
  between consecutive shots, unless the cut is meant to surprise.
- Low camera (elevation 2-8) feels heroic and premium; high (20-40) feels calm and overseeing.
- fill 0.45 wide, 0.6 medium, 0.9 close; a close-up (0.9+) is for the label or the cap.
- Depth of field (`aperture`) keeps the product sharp and softens what's behind it: use the style's on most
  shots, wider (2-2.8) on close-ups and the hero to set the product apart, 0 on a wide shot whose set should read.
- The last shot is the hero: static, from the front (azimuth near 0), fill 0.45-0.6, with the brand
  name as a title over it. It lasts at least 2.5 s and the name appears at least 0.4 s into it.
- Titles: the brand name in the brand's font from the brand profile (size 0.06-0.13), an optional tagline
  (0.025-0.035) under it; placed under the product (y 0.8-0.93) so they don't cover it; at most 2 on screen.
- Script is for words in lower or mixed case ("Aurelle", "Skin, simply."), never all capitals; light
  titles on a dark set, dark on a light one.
- Colours (backdrop, pedestal, titles) come from the brand's palette or sit well with it; follow every
  "do not" in the brand profile.
- Start from the style that fits the brief and the brand, then adapt its colours to the palette.

## Styles

Starting points: take the one that fits, then adapt its colours to the brand's palette.

- `luxury_dark`: for perfume, spirits, jewellery, watches: luxurious, moody, premium. Near-black set, rim lights tracing the glass, lights rising from dark; slow, low camera; wide-spaced serif. Lighting `rim_dark`; titles `serif` #ECE4D2, tagline `sans`; shots 3-4 s; moves reveal, orbit, dolly, static; aperture f/2.8.
- `clean_minimal`: for skincare, wellness, home, tech accessories: clean, calm, bright, minimal. Light set in the product's paler colours, soft even light, unhurried; dark type on light. Lighting `high_key`; titles `serif` #3C342E, tagline `script`; shots 3-3.5 s; moves static, dolly, orbit; aperture f/5.6.
- `bold_energetic`: for drinks, snacks, sport, gaming: bold, loud, energetic, young. Dark set, two coloured lights, glow; fast cuts that each snap to a stop (ease out); the product spins (a rotation track); big condensed type. Lighting `neon_dual`; titles `condensed` #FF5AB0, tagline `sans_bold`; shots 1.2-1.8 s; moves orbit, dolly, crane, truck, static; aperture f/4.
- `natural_organic`: for food, oils, coffee, tea, natural cosmetics: warm, natural, earthy, honest. Wood-brown set, warm light from above like a window; gentle crane and orbit; warm cream serif. Lighting `top_soft`; titles `serif` #E8DCB8, tagline `serif`; shots 3-3.5 s; moves crane, orbit, static; aperture f/4.
- `warm_glow`: for serums, oils, candles, amber glass: warm, glowing, radiant, premium. Dark warm set, warm rims and glow through the glass; light rising; amber type. Lighting `rim_dark`; titles `sans_bold` #F2A24A, tagline `sans`; shots 3-4 s; moves zoom, orbit, static; aperture f/2.8.
- `tech_sleek`: for electronics, devices, tools, cars, men's grooming: sleek, precise, modern, cool. Blue-black glossy set, hard cool side light, crisp contrast; precise sideways and push moves; thin wide-spaced sans. Lighting `split`; titles `sans` #E6EEF5, tagline `sans`; shots 2-2.5 s; moves truck, dolly, orbit, static; aperture f/5.6.
- `playful_pop`: for toys, sweets, beauty for teens, fun gadgets: playful, cheerful, colourful. A saturated set from the brand's brightest colour, a contrasting pedestal, bright even light; bouncy moves, a spin; chunky type. Lighting `three_point`; titles `sans_bold` #2B1B4A, tagline `sans_bold`; shots 1.5-2.2 s; moves crane, orbit, dolly, static; aperture f/8.
- `soft_pastel`: for beauty, fragrance, baby care, gifts: soft, delicate, romantic, feminine. Blush set, soft light from above with a little glow; slow drifting orbit; script name. Lighting `top_soft`; titles `script` #7A4E55, tagline `sans`; shots 3-4 s; moves orbit, dolly, static; aperture f/2.8.
