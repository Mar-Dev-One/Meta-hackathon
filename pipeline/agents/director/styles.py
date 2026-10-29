"""The style library: looks the director starts from and adapts to the
brand (its palette, its mood, its do-nots). Each is a whole `Look` (set,
light, environment) that renders well, the titles' type, the pacing and
the camera moves and the depth of field that suit it. The first five are
the hand-made ads' (pipeline/demos/ads.py).

    style = STYLES["luxury_dark"]
    Storyboard(look=style.look, ...)
"""

from pydantic import Field

from pipeline.schemas.storyboard import (HEX, Backdrop, CameraMove, Ease, Environment, Font, Lighting, Look,
                                         Pedestal, Product, Shot, Storyboard, Strict, Title)


class TitleStyle(Strict):
    font: Font
    color: str = Field(pattern=HEX)
    size: float = Field(description="share of the frame's height")
    tracking: float
    tagline_font: Font
    tagline_color: str = Field(pattern=HEX)


class Style(Strict):
    name: str
    use_for: str = Field(description="briefs and products it suits")
    look: Look
    title: TitleStyle
    shot_seconds: tuple[float, float] = Field(description="a shot's length, shortest to longest")
    moves: list[str] = Field(description="the camera moves that suit it, most typical first")
    ease: Ease = "in_out"
    aperture: float = Field(description="its usual f-number for depth of field (0 = all sharp): wider (2-2.8) "
                                        "on close-ups and the hero, the set softening behind the product")
    notes: str = Field(description="what makes it work")


STYLES: dict[str, Style] = {s.name: s for s in [
    Style(
        name="luxury_dark", use_for="perfume, spirits, jewellery, watches: luxurious, moody, premium",
        look=Look(environment=Environment(), backdrop=Backdrop(color="#0A0A0C"),
                  pedestal=Pedestal(width=0.32, height=0.22, color="#0E0E10"),
                  lighting=Lighting(preset="rim_dark", fade_in=2.5)),
        title=TitleStyle(font="serif", color="#ECE4D2", size=0.075, tracking=0.25,
                         tagline_font="sans", tagline_color="#C9A45C"),
        shot_seconds=(3, 4), moves=["reveal", "orbit", "dolly", "static"], aperture=2.8,
        notes="near-black set, rim lights tracing the glass, lights rising from dark; slow, low camera; wide-spaced serif"),
    Style(
        name="clean_minimal", use_for="skincare, wellness, home, tech accessories: clean, calm, bright, minimal",
        look=Look(environment=Environment(ambient_strength=0.6, bloom=0.03, tonemap="neutral"),
                  background=[0.75, 0.73, 0.70], backdrop=Backdrop(color="#E7E3DD", roughness=0.85),
                  pedestal=Pedestal(width=0.2, height=0.1, color="#F1EEE9", roughness=0.7),
                  lighting=Lighting(preset="high_key")),
        title=TitleStyle(font="serif", color="#3C342E", size=0.07, tracking=0.2,
                         tagline_font="script", tagline_color="#8C7864"),
        shot_seconds=(3, 3.5), moves=["static", "dolly", "orbit"], aperture=5.6,
        notes="light set in the product's paler colours, soft even light, unhurried; dark type on light"),
    Style(
        name="bold_energetic", use_for="drinks, snacks, sport, gaming: bold, loud, energetic, young",
        look=Look(environment=Environment(bloom=0.14), background=[0.01, 0.003, 0.015],
                  backdrop=Backdrop(color="#140A1C", roughness=0.5),
                  pedestal=Pedestal(width=0.2, height=0.12, color="#1A1020", roughness=0.4),
                  lighting=Lighting(preset="neon_dual", intensity=1.2)),
        title=TitleStyle(font="condensed", color="#FF5AB0", size=0.13, tracking=0.04,
                         tagline_font="sans_bold", tagline_color="#FFFFFF"),
        shot_seconds=(1.2, 1.8), moves=["orbit", "dolly", "crane", "truck", "static"], ease="out", aperture=4,
        notes="dark set, two coloured lights, glow; fast cuts that each snap to a stop (ease out); the product "
              "spins (a rotation track); big condensed type"),
    Style(
        name="natural_organic", use_for="food, oils, coffee, tea, natural cosmetics: warm, natural, earthy, honest",
        look=Look(environment=Environment(ambient_strength=0.12, exposure=1.1), background=[0.03, 0.02, 0.012],
                  backdrop=Backdrop(color="#2A1D13", roughness=0.7),
                  pedestal=Pedestal(width=0.34, height=0.08, color="#5B3D25", roughness=0.6),
                  lighting=Lighting(preset="top_soft", warmth=0.6)),
        title=TitleStyle(font="serif", color="#E8DCB8", size=0.075, tracking=0.2,
                         tagline_font="serif", tagline_color="#D9B86A"),
        shot_seconds=(3, 3.5), moves=["crane", "orbit", "static"], aperture=4,
        notes="wood-brown set, warm light from above like a window; gentle crane and orbit; warm cream serif"),
    Style(
        name="warm_glow", use_for="serums, oils, candles, amber glass: warm, glowing, radiant, premium",
        look=Look(environment=Environment(bloom=0.12), background=[0.012, 0.007, 0.004],
                  backdrop=Backdrop(color="#120C08"),
                  pedestal=Pedestal(width=0.22, height=0.16, color="#0B0806", roughness=0.9),
                  lighting=Lighting(preset="rim_dark", warmth=0.5, intensity=1.2, fade_in=2.0)),
        title=TitleStyle(font="sans_bold", color="#F2A24A", size=0.075, tracking=0.18,
                         tagline_font="sans", tagline_color="#E8D8C0"),
        shot_seconds=(3, 4), moves=["zoom", "orbit", "static"], aperture=2.8,
        notes="dark warm set, warm rims and glow through the glass; light rising; amber type"),
    Style(
        name="tech_sleek", use_for="electronics, devices, tools, cars, men's grooming: sleek, precise, modern, cool",
        look=Look(environment=Environment(ambient_strength=0.05, bloom=0.05, tonemap="aces"),
                  background=[0.006, 0.008, 0.012], backdrop=Backdrop(color="#0D1015", roughness=0.35),
                  pedestal=Pedestal(width=0.3, height=0.06, color="#14181F", roughness=0.3),
                  lighting=Lighting(preset="split", warmth=-0.5, intensity=1.4)),
        title=TitleStyle(font="sans", color="#E6EEF5", size=0.065, tracking=0.35,
                         tagline_font="sans", tagline_color="#7FA8C9"),
        shot_seconds=(2, 2.5), moves=["truck", "dolly", "orbit", "static"], aperture=5.6,
        notes="blue-black glossy set, hard cool side light, crisp contrast; precise sideways and push moves; "
              "thin wide-spaced sans"),
    Style(
        name="playful_pop", use_for="toys, sweets, beauty for teens, fun gadgets: playful, cheerful, colourful",
        look=Look(environment=Environment(ambient_strength=0.5, bloom=0.04, tonemap="neutral"),
                  background=[0.9, 0.62, 0.12], backdrop=Backdrop(color="#FFC94A", roughness=0.8),
                  pedestal=Pedestal(width=0.24, height=0.1, color="#FF7AA8", roughness=0.7),
                  lighting=Lighting(preset="three_point", intensity=1.1)),
        title=TitleStyle(font="sans_bold", color="#2B1B4A", size=0.11, tracking=0.02,
                         tagline_font="sans_bold", tagline_color="#FFFFFF"),
        shot_seconds=(1.5, 2.2), moves=["crane", "orbit", "dolly", "static"], ease="out", aperture=8,
        notes="a saturated set from the brand's brightest colour, a contrasting pedestal, bright even light; "
              "bouncy moves, a spin; chunky type"),
    Style(
        name="soft_pastel", use_for="beauty, fragrance, baby care, gifts: soft, delicate, romantic, feminine",
        look=Look(environment=Environment(ambient_strength=0.45, bloom=0.08, tonemap="neutral"),
                  background=[0.78, 0.66, 0.64], backdrop=Backdrop(color="#EBD5D0", roughness=0.9),
                  pedestal=Pedestal(width=0.26, height=0.14, color="#F6E9E4", roughness=0.8),
                  lighting=Lighting(preset="top_soft", warmth=0.25)),
        title=TitleStyle(font="script", color="#7A4E55", size=0.08, tracking=0.0,
                         tagline_font="sans", tagline_color="#9C7A7E"),
        shot_seconds=(3, 4), moves=["orbit", "dolly", "static"], aperture=2.8,
        notes="blush set, soft light from above with a little glow; slow drifting orbit; script name"),
]}


def sample(style: Style, product: Product | None = None, name: str = "AURELLE", tagline: str = "Eau de parfum",
           seconds: float = 3.0) -> Storyboard:
    """One hero shot in the style, with its titles: to see what it looks like."""
    t = style.title
    return Storyboard(
        title=f"{style.name} sample", brief=f"a sample of the {style.name} style", style=style.name, look=style.look,
        product=product or Product(template="perfume"),
        shots=[Shot(id="s1", intent="the hero, the name below", duration=seconds,
                    camera=CameraMove(move="static", elevation=4, fill=0.5, aperture=style.aperture))],
        titles=[Title(text=name.title() if t.font == "script" else name, font=t.font, size=t.size, y=0.82, color=t.color, tracking=t.tracking, start=0.3),
                Title(text=tagline, font=t.tagline_font, size=0.03, y=0.91, color=t.tagline_color,
                      tracking=0.1, start=0.5)])


if __name__ == "__main__":
    import asyncio

    from PIL import Image, ImageDraw, ImageFont

    from pipeline.runs import Run
    from pipeline.studio import Studio, build

    async def main() -> None:
        """Every style's sample, side by side, as styles.png in a run."""
        with Run.create("styles") as run:
            async with Studio() as studio:
                run.watch(studio)
                tiles = []
                for style in STYLES.values():
                    length = await build(studio, sample(style))
                    frame = await studio.call("shot.preview", times=[length - 0.05], width=640, height=360,
                                              out_dir=str(run.folder("frames", style.name)))
                    tiles.append((style.name, Image.open(frame["frames"][0]["path"]).convert("RGB")))
            sheet = Image.new("RGB", (4 * 640 + 30, 2 * (360 + 34)), (255, 255, 255))
            draw = ImageDraw.Draw(sheet)
            font = ImageFont.load_default(size=22)
            for i, (name, tile) in enumerate(tiles):
                x, y = (i % 4) * 650, (i // 4) * 394
                sheet.paste(tile, (x, y))
                draw.text((x + 6, y + 364), name, fill=(30, 30, 30), font=font)
            sheet.save(run.path("styles.png"))
            run.output("styles", run.root / "styles.png")
        print(run.root / "styles.png")

    asyncio.run(main())
