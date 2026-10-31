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
- `fill`: how much of the frame's height the subject fills, as seen from the camera's elevation, 0.05 to 5 (default 0.6); up to 0.97 it's whole in the frame, over that it's cropped; in a narrow frame a wide subject is held by the width, and over 0.7 its sides crop
- `azimuth`: degrees around the subject: 0 = front (+Z), 90 = its right (+X) (default 0)
- `elevation`: degrees above the subject, -85 to 85 (default 10)
- `fov_degrees`: vertical field of view (default 30)
- `aperture`: depth of field: the f-number, the focus kept on the subject's near side and the aperture never wider than keeps the subject itself sharp; 0 = everything sharp (default), 2-2.8 a very soft background, 4-5.6 a softened set, 8+ nearly all sharp
- `to_azimuth`: orbit: where it ends (default azimuth + 60)
- `from_fill`: dolly: the framing it starts from (default fill * 0.6: pushes in)
- `to_fill`: dolly: the framing it ends on (default fill)
- `from_elevation`: crane: start (default elevation - 15)
- `to_elevation`: crane: end (default elevation + 25)
- `travel`: truck: meters moved to the right, negative for left (default: most of the room beside the subject in the frame, so it stays whole)
- `from`: reveal: where the aim starts, above (default), below, left or right
- `from_fov`: zoom: start lens (default fov_degrees * 1.5)
- `to_fov`: zoom: end lens (default fov_degrees)

## Shots (`shots[]`)

- `id`: s1, s2, ...
- `intent`: what the shot is for, in a sentence: the critic judges it against this
- `duration` (>0.2 .. 30): seconds; shots run back to back from 0
- `transition` (cut | dip, default cut): how the ad comes into this shot from the one before: cut (straight in) or dip (a brief fade through black: a pause, a change of place or time)

## Product motion (`shots[].motion`)

The product itself moving during a shot, while the camera does its move; it's back at rest at the next cut. Null (the default) keeps it still.

- `move` (turn | float | drop | tilt): turn: turns on its own axis and settles facing front by the end (shows the label coming round); float: rises gently, weightless, through the shot; drop: falls onto its stand in the shot's first 40%, then holds still; tilt: leans gently towards the camera and back
- `amount` (-720 .. 720): turn: degrees it turns (default 45; 360 a full spin; negative the other way); tilt: degrees it leans (default 8); float: how far it rises and drop: how far above it starts, as a share of its height (defaults 0.08 and 0.35)

## Light (`look.lighting`)

Presets: three_point, rim_dark (luxury, moody), high_key (clean, bright), top_soft, split (dramatic) or neon_dual (bold).

- `preset` (three_point | rim_dark | high_key | top_soft | split | neon_dual): rim_dark: luxury, moody; high_key: clean, bright (light backdrop); top_soft: natural, skylight; split: dramatic; neon_dual: bold, energetic; three_point: neutral
- `intensity` (0 .. 20, default 1.0): times the preset's brightness
- `turn` (-360 .. 360, default 0.0): degrees to turn the whole setup around the product
- `warmth` (-1 .. 1, default 0.0): -1 cooler .. 1 warmer
- `fade_in` (>0 .. 10): seconds over which every light rises from dark at the start (a reveal)
- `glow` (0 .. 20): a soft pool of light on the wall behind the product: glass lights up in it in the colour of what it holds (a backlit bottle); 1 subtle, 2-3 strong; for glass on a dark set
- `glow_color`: the glow's colour (default warm)

## The set (`look`)

- `background` (default [0.004, 0.004, 0.006]): linear RGB where nothing is drawn (behind the backdrop's edges)

`look.environment`:

- `hdri` (default studio): the light environment around the product: it lights it, shows in its reflections (glass and metal read by it) and, with show_skybox, is the background. By name: studio: a small photo studio: soft, neutral light (the default); studio_bright: a large bright photo studio: clean, even, high key; studio_warm: a studio with warm brown walls: cosy, crafted; fireplace: a room lit by a fire: warm, intimate, evening; golden_hour: open land at sunrise: golden, natural, hopeful; sunset_sky: a blazing orange sunset sky: dramatic, bold; daylight: a clear blue sky with soft clouds: fresh, outdoors; city_night: a city's lights at night: urban, energetic, nightlife (or an HDRI's path under the Studio's assets)
- `use_ibl` (default True): light and reflect with the light environment (keep on for glass and metal)
- `show_skybox` (default False): show the light environment as the background, blurred by sky_blur; needs look.backdrop null (the backdrop's wall hides it)
- `sky_blur` (0 .. 1, default 0.35): how soft the background environment is: 0.2 recognisable, 0.35 a soft photographic blur, 0.6 only colour and light
- `painted`: a background painted for this ad by Muse Image, from this description of a place, its light and colours (e.g. 'a sunlit limestone bathroom, palm leaf shadows, warm morning light'): shown behind the product, blurred by sky_blur, and lighting it, in place of `hdri` (and of the backdrop); for a place the library doesn't have
- `ambient_strength` (0 .. 4, default 0.06): 0.05 dark and moody, 0.6 bright and airy
- `exposure` (>0 .. 16, default 1.0)
- `bloom` (0 .. 1, default 0.08): glow around bright highlights; 0.03 clean, 0.14 dreamy or neon
- `tonemap` (agx | aces | neutral, default agx): agx: soft filmic; aces: contrasty; neutral: colours as authored (bright, clean looks)
- `ssao` (default True)

`look.backdrop` (a cyclorama: a floor curving up into a wall; or null: the light environment is the background):

- `color` (default #0A0A0C): the cyclorama's colour (sRGB)
- `roughness` (0 .. 1, default 0.6)
- `surface` (cream_marble | granite | terrazzo | dark_wood | light_wood | concrete | stone | sand | plaster | blue_linen | red_velvet): null: plain `color`. Or a real material for it from the set library (its colour comes from the material; `color` is unused): cream_marble: warm cream marble with soft veins, polished: luxury, timeless; granite: dark grey speckled granite: luxury, masculine, tech; terrazzo: terrazzo, flecks in warm stone: modern, playful, design; dark_wood: dark reddish-brown wood: warm, crafted, premium; light_wood: light warm wood veneer: natural, Scandinavian, calm; concrete: smooth grey-brown concrete: urban, minimal, raw; stone: rough brown natural rock: outdoors, rugged, organic; sand: fine pale beach sand: summer, sun care, coastal; plaster: warm beige plaster: soft, natural, skincare (a wall); blue_linen: soft blue linen cloth: fresh, calm, home; red_velvet: deep red velvet: luxury, evening, romance

`look.pedestal` (or null: the product stands on the floor):

- `width` (>0.02 .. 3, default 0.32): diameter, meters; a little wider than the product
- `height` (>0.01 .. 2, default 0.2): meters; the product stands on it
- `color` (default #0E0E10)
- `roughness` (0 .. 1, default 0.85): keep high (0.8+) under rim lights, or its top glares
- `surface` (cream_marble | granite | terrazzo | dark_wood | light_wood | concrete | stone | sand | plaster | blue_linen | red_velvet): null: plain `color`. Or a material (see look.backdrop.surface); a low wide pedestal of one is a slab to stand the product on

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

## End card (`end_card`)

A still the film dissolves into after the last shot: the product as photographed, the name under it, a short line under that, on a plain colour (text light or dark to suit). It counts in the ad's length: the shots and the card together make it.

- `seconds` (1.5 .. 4, default 2.5): how long it adds after the last shot (its dissolve begins a little before the film ends)
- `name`: the brand's name as it should read
- `tagline`: a short line under the name, or null
- `background`: the card's colour: from the brand's palette, calm and solid
- `font` (serif | sans | sans_bold | condensed | script): the name's font, as the titles'

## Other animation (`tracks[]`)

Keys on any number field of an entity, eased between: for the lights (`light_*`), e.g. one rising or dimming at a cut. For the product moving, use the shots' `motion`, not a track.

## Ad craft

- Open strong: the product is on screen and readable within the first 2 seconds.
- 3 to 6 shots for 15 seconds; no shot under 1.2 s or over 5 s (the style sets the pace).
- Every shot moves differently from the one before (orbit, then dolly, then crane ...): cuts land on motion.
- Every cut changes the picture clearly, not just the move: where a shot ends and the next begins, change the
  side by 30 degrees or more, the height by 12 or more, or the size clearly (wide 0.4, medium 0.6, close 0.9),
  or it's a jump cut that reads as a stutter. Vary the framings across the ad: wide, close, from the side, from
  above, not one medium shot after another.
  Cuts fall on the music's beats by themselves (shot lengths are nudged a little to meet them).
- Most shots come in on a straight cut. A `dip` (a brief fade through black) is a breath: use one or two in a
  slow, luxurious or calm ad, before the hero or where the film changes place, angle or time; none in a fast,
  energetic one, where cuts are the rhythm.
- Keep the side of the product steady across cuts: don't jump more than about 90 degrees of azimuth
  between consecutive shots, unless the cut is meant to surprise.
- Bring the product to life: give one to three shots a `motion` (a drop to open, a turn to bring the label
  round, a float for something light or dreamy). A moving product against a calm camera reads best: pair a
  motion with a static, slow dolly or slow crane, not with a fast orbit. Keep the hero's motion gentle (a
  turn that settles facing front, or none) so the name lands on a still product.
- Low camera (elevation 2-8) feels heroic and premium; high (20-40) feels calm and overseeing.
- fill 0.45 wide, 0.6 medium, 0.9 close; a close-up (0.9+) is for the label or the cap.
- A truck slides only as far as there's room beside the product, so it stays whole (a longer `travel` is cut
  back): for a wide product (a shoe, headphones, a controller), frame the truck wide (fill 0.4-0.5) to give it room.
- Depth of field (`aperture`) keeps the product sharp and softens what's behind it: use the style's on most
  shots, wider (2-2.8) on close-ups and the hero to set the product apart, 0 on a wide shot whose set should read.
- Glass (a see-through product) shows what's behind it: on a dark set, light it strongly (`intensity` 1.5-2)
  and give it a `glow` (2-3), a warm pool on the wall behind, so the glass lights up in its liquid's colour. A
  lighter backdrop doesn't help: the glass blends into it. The glow is behind the product as seen from the
  front: keep glass shots within about 35 degrees of azimuth 0, or the glass turns dark.
- Glass and metal reflect their surroundings: keep `environment.use_ibl` on.
- Separate the product from the set: the backdrop clearly darker or lighter than the product (a white jar on a
  mid or dark set, a dark product on a lighter one, or a rim-lit dark product on black with strong light).
- Titles must read against what's behind them (the backdrop, and the pedestal for titles low in the frame):
  light on dark, dark on light, a contrast ratio of at least 3.
- The last shot is the hero: static, from the front (azimuth near 0), fill 0.4-0.5 (room for the name), with the brand
  name as a title over it. It lasts at least 2.5 s and the name appears at least 0.4 s into it.
- Titles: the brand name in the brand's font from the brand profile (size 0.06-0.13), an optional tagline
  (0.025-0.035) with it; at most 2 on screen. Place them where the frame is empty set, never over the product
  or on the pedestal's face: above the product (y 0.08-0.25, the tagline under the name), or below the pedestal
  when the hero is framed wide enough to leave set there. A pedestal runs down from the product's base for
  `fill` times its height over the product's.
- End on an end card (2-3 s) unless the brief is very short: the brand's name as its titles have it, the tagline
  if there is one, on a solid colour from the palette that suits the film's last frame (dark after a dark film,
  light after a light one). Plan the shots for the ad's length minus the card.
- Script is for words in lower or mixed case ("Aurelle", "Skin, simply."), never all capitals; light
  titles on a dark set, dark on a light one.
- Colours (backdrop, pedestal, titles) come from the brand's palette or sit well with it. The brand profile's
  "do not"s are its usual taste: follow them unless the brief asks otherwise, in which case the brief wins.
- The set is sized for the product: a pedestal 1.2-7 times its width and at most 1.5 times its height.
- Choose a set that tells the brand's story, not a default: a surface for the product to stand on (a low,
  wide pedestal of one is a slab: cream_marble for luxury, dark_wood for crafted warmth, sand for summer,
  stone for the outdoors, red_velvet for evening) and a light environment that suits the mood (studio for
  clean product shots, fireplace for intimate warmth, golden_hour for natural products, city_night for bold
  nightlife). Plain colours are still right for a minimal brand.
- A real background: set look.backdrop to null and environment.show_skybox to true, and the light environment
  stands behind the product, softly blurred (sky_blur 0.3-0.4): a lifestyle shot rather than a studio one.
  Glass reads best this way: it shows the light behind it, clear and bright, where a dark wall turns it black.
- A place the library doesn't have (a sunlit bathroom, a spa, a café terrace, a kitchen at dawn, a desk by a
  window): describe it in environment.painted and Muse Image paints it for this ad, the brand's colours in its
  light and materials. Describe a place and its light, never the product; keep it calm behind the product.
  When the brief names a place (a kitchen, a spa, a bathroom, a beach bar), the ad is set there: paint it,
  unless a light environment in the library is that very place.
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
- `marble_luxury`: for perfume, jewellery, watches, premium skincare: luxurious, timeless, refined. A polished marble slab in a warm, softly blurred room; clear even light that makes glass sparkle; slow, close moves; dark serif. Lighting `three_point`; titles `serif` #2E241C, tagline `sans`; shots 3-4 s; moves dolly, orbit, static; aperture f/2.8.
- `golden_outdoors`: for oils, natural cosmetics, drinks, sun care, food: natural, warm, honest, fresh. A natural stone in an open field at sunrise, blurred behind; warm light from above; gentle crane; cream serif. Lighting `top_soft`; titles `serif` #FFF6E5, tagline `sans`; shots 3-3.5 s; moves crane, dolly, orbit, static; aperture f/2.8.
- `evening_fireplace`: for fragrance, spirits, candles, chocolate, cosy home: intimate, warm, rich. Dark wood before a glowing fire, deeply blurred; warm rims; slow and close, shallow focus; cream serif. Lighting `rim_dark`; titles `serif` #F6E7C8, tagline `sans`; shots 3-4 s; moves orbit, dolly, static; aperture f/2.
- `city_nights`: for tech, sneakers, drinks, streetwear, nightlife: urban, bold, energetic, modern. A granite slab against blurred city lights at night; hard cool side light, bloom; quick precise moves; bold white sans. Lighting `split`; titles `sans_bold` #FFFFFF, tagline `sans`; shots 1.8-2.5 s; moves truck, orbit, dolly, static; aperture f/2.8.
- `summer_beach`: for sun care, drinks, swimwear, summer launches: sunny, fresh, carefree. Fine sand under a clear blue sky, softly blurred; bright sunny light; lively moves; bold white sans. Lighting `high_key`; titles `sans_bold` #FFFFFF, tagline `sans`; shots 2-3 s; moves crane, orbit, dolly, static; aperture f/4.
