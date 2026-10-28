"""Writes a font's kerning pairs as JSON next to it, for the Studio's text.

stb_truetype (Engine/src/Text/Font.c) can't read the kerning in most
current fonts: they keep it in OpenType GPOS lookups (often wrapped in
Extension lookups) that it skips. fontTools reads them all, so this runs
once per font and Font.c reads the result.

    python scripts/font_kerning.py Assets/fonts/*.ttf

writes Assets/fonts/<font>.kern.json:

    {"font": "PlayfairDisplay.ttf", "units_per_em": 1000,
     "pairs": [[65, 86, -50], ...]}          # left codepoint, right codepoint, font units

Only characters the Studio is likely to set are covered (ASCII, Latin-1,
common punctuation), and only pairs that move. Variable fonts give their
default instance's values.
"""

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

# What titles use: ASCII, Latin-1 letters, typographic quotes and dashes.
CHARACTERS = ([chr(c) for c in range(0x20, 0x7F)] + [chr(c) for c in range(0xA0, 0x100)]
              + list("–—‘’“”…•€™"))


def kern_lookups(font: TTFont) -> list:
    """The GPOS lookups the 'kern' feature uses (for any script), in order."""
    table = font["GPOS"].table
    features = table.FeatureList.FeatureRecord
    indices = set()
    for record in features:
        if record.FeatureTag == "kern":
            indices.update(record.Feature.LookupListIndex)
    return [table.LookupList.Lookup[i] for i in sorted(indices)]


def pair_subtables(lookup) -> list:
    """A lookup's pair-adjustment subtables, unwrapping Extension lookups."""
    out = []
    for sub in lookup.SubTable:
        if lookup.LookupType == 9:
            if sub.ExtensionLookupType != 2:
                continue
            sub = sub.ExtSubTable
        elif lookup.LookupType != 2:
            continue
        out.append(sub)
    return out


def x_advance(value) -> int:
    return getattr(value, "XAdvance", 0) or 0 if value is not None else 0


def pair_value(subtables: list, left: str, right: str) -> tuple[bool, int]:
    """(matched, adjustment) for one lookup: the first subtable that covers
    the left glyph and has the pair decides, as OpenType applies them."""
    for sub in subtables:
        if left not in sub.Coverage.glyphs:
            continue
        if sub.Format == 1:
            pair_set = sub.PairSet[sub.Coverage.glyphs.index(left)]
            for record in pair_set.PairValueRecord:
                if record.SecondGlyph == right:
                    return True, x_advance(record.Value1)
        elif sub.Format == 2:
            c1 = sub.ClassDef1.classDefs.get(left, 0)
            c2 = sub.ClassDef2.classDefs.get(right, 0)
            return True, x_advance(sub.Class1Record[c1].Class2Record[c2].Value1)
    return False, 0


def legacy_kern(font: TTFont) -> dict:
    """Pairs from an old-style 'kern' table, by glyph name."""
    pairs = {}
    if "kern" in font:
        for table in font["kern"].kernTables:
            pairs.update(getattr(table, "kernTable", {}))
    return pairs


def kerning(path: Path) -> dict:
    font  = TTFont(path)
    cmap  = font.getBestCmap()
    chars = [(ord(c), cmap[ord(c)]) for c in CHARACTERS if ord(c) in cmap]
    lookups = [pair_subtables(l) for l in kern_lookups(font)] if "GPOS" in font else []
    legacy  = legacy_kern(font)

    pairs = []
    for left_cp, left in chars:
        # Only lookups that cover this left glyph can move it.
        relevant = [subs for subs in lookups if any(left in s.Coverage.glyphs for s in subs)]
        for right_cp, right in chars:
            value = 0
            for subs in relevant:
                matched, v = pair_value(subs, left, right)
                if matched:
                    value += v
            if not lookups:
                value = legacy.get((left, right), 0)
            if value:
                pairs.append([left_cp, right_cp, value])
    return {"font": path.name, "units_per_em": font["head"].unitsPerEm, "pairs": pairs}


def main(paths: list[str]) -> None:
    for name in paths:
        path = Path(name)
        result = kerning(path)
        out = path.with_suffix(".kern.json")
        out.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        print(f"{path.name}: {len(result['pairs'])} pairs -> {out.name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
