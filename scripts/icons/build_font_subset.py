#!/usr/bin/env python3
"""Build the Material Icons subset the control SPA ships.

The upstream ``material-icons`` package ships every icon Google publishes —
~2,200 glyphs, 125 kB of WOFF2 — and the SPA loads it on first paint to draw
a few dozen. This script cuts it down to exactly the icons listed in
``frontend/src/icons.ts``.

Run it after adding an icon to that list::

    pip install fonttools brotli
    python3 scripts/icons/build_font_subset.py

Commit the regenerated ``frontend/src/fonts/material-icons-subset.woff2``
together with the change that needed the new icon.

Why this is more than ``pyftsubset --text=...``: Material Icons is a
*ligature* font. ``<span class="material-icons">expand_more</span>`` is the
literal text "expand_more", which the font's GSUB ``liga`` table rewrites
into one icon glyph. Subsetting by text would keep the 26 letters and, via
layout closure, drag every ligature they can spell back in — which is to
say, the whole font. So this script resolves each ligature to the private-use
codepoint of the glyph it produces, and subsets by *those* codepoints with
layout closure disabled.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ICONS_TS = REPO / "frontend" / "src" / "icons.ts"
SOURCE_FONT = (
    REPO / "frontend" / "node_modules" / "material-icons" / "iconfont"
    / "material-icons.woff2"
)
# Lives under src/, not public/: the backend mounts its own scoreboard-font
# directory at /fonts (see app/bootstrap._register_static_mounts), which
# shadows anything the SPA would serve from public/fonts. As a src/ asset
# Vite fingerprints it into /assets/ instead, which nothing shadows and
# which gets a content hash for free.
OUTPUT = REPO / "frontend" / "src" / "fonts" / "material-icons-subset.woff2"

# The letters a ligature is spelled with. Kept in the subset because the
# shaper still matches on them before substituting; dropping them would
# leave nothing for the ``liga`` rules to fire on.
LIGATURE_ALPHABET = "abcdefghijklmnopqrstuvwxyz_"


def read_icon_names() -> list[str]:
    """Pull the icon names out of ``icons.ts`` without running a JS engine."""
    text = ICONS_TS.read_text(encoding="utf-8")
    names: list[str] = []
    for block in ("LITERAL_ICONS", "DYNAMIC_ICONS"):
        m = re.search(rf"{block}\s*=\s*\[(.*?)\]\s*as const", text, re.S)
        if not m:
            raise SystemExit(f"Could not find {block} in {ICONS_TS}")
        names.extend(re.findall(r"'([a-z0-9_]+)'", m.group(1)))
    return sorted(set(names))


def ligature_features(font) -> list[str]:
    """Return the GSUB feature tags that carry ligature substitutions.

    Read from the font rather than hardcoded, because the obvious guess is
    wrong: Material Icons ships its substitutions under ``rlig`` (required
    ligatures), not ``liga``, even though every published snippet sets
    ``font-feature-settings: 'liga'`` — ``rlig`` is on by default, so the
    CSS never had to name the real feature. Passing the wrong tag to
    pyftsubset drops the only lookup the font has and yields a font whose
    icons render as their literal names.
    """
    tags = {
        record.FeatureTag
        for record in font["GSUB"].table.FeatureList.FeatureRecord
    }
    ligature_tags = sorted(tags & {"rlig", "liga", "dlig", "clig"})
    if not ligature_tags:
        raise SystemExit(
            f"No ligature feature in the source font (saw: {sorted(tags)})"
        )
    return ligature_tags


def build_ligature_map(font) -> dict[str, str]:
    """Map ligature text (``"expand_more"``) to its output glyph name."""
    cmap = font.getBestCmap()
    codepoint_of_glyph: dict[str, int] = {}
    for cp, glyph in cmap.items():
        codepoint_of_glyph.setdefault(glyph, cp)

    ligatures: dict[str, str] = {}
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            table = getattr(subtable, "ligatures", None)
            if not table:
                continue
            for first, entries in table.items():
                for entry in entries:
                    sequence = [first, *entry.Component]
                    try:
                        text = "".join(
                            chr(codepoint_of_glyph[g]) for g in sequence
                        )
                    except KeyError:
                        # A component with no cmap entry cannot be typed,
                        # so it is not a ligature we could ever trigger.
                        continue
                    ligatures[text] = entry.LigGlyph
    return ligatures


def main() -> int:
    try:
        from fontTools.ttLib import TTFont
    except ImportError as exc:
        raise SystemExit(
            "fonttools is required: pip install fonttools brotli"
        ) from exc

    if not SOURCE_FONT.exists():
        raise SystemExit(
            f"{SOURCE_FONT} is missing — run `npm ci` in frontend/ first."
        )

    wanted = read_icon_names()
    font = TTFont(SOURCE_FONT)
    ligatures = build_ligature_map(font)
    cmap = font.getBestCmap()
    codepoint_of_glyph = {}
    for cp, glyph in cmap.items():
        codepoint_of_glyph.setdefault(glyph, cp)

    missing = [name for name in wanted if name not in ligatures]
    if missing:
        raise SystemExit(
            "These names are not ligatures in the upstream font (typo, or "
            "renamed upstream): " + ", ".join(missing)
        )

    icon_codepoints = {codepoint_of_glyph[ligatures[n]] for n in wanted}
    alphabet_codepoints = {ord(c) for c in LIGATURE_ALPHABET}
    unicodes = ",".join(
        f"U+{cp:04X}" for cp in sorted(icon_codepoints | alphabet_codepoints)
    )

    features = ligature_features(font)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "subset.woff2"
        subprocess.run(
            [
                sys.executable, "-m", "fontTools.subset",
                str(SOURCE_FONT),
                f"--unicodes={unicodes}",
                # Keep the ligature feature — it is the entire mechanism.
                f"--layout-features={','.join(features)}",
                # Without this, closure re-adds every icon whose name can be
                # spelled from the alphabet above: the whole font (measured:
                # 115 kB and 2,082 ligatures, versus 5 kB and ours).
                "--no-layout-closure",
                "--flavor=woff2",
                f"--output-file={staged}",
            ],
            check=True,
        )
        verify(staged, wanted)
        data = staged.read_bytes()

    before = SOURCE_FONT.stat().st_size
    OUTPUT.write_bytes(data)
    after = len(data)
    print(f"{len(wanted)} icons, features {features}")
    print(f"{before:,} B -> {after:,} B ({100 - after * 100 // before}% smaller)")
    print(f"wrote {OUTPUT.relative_to(REPO)}")
    return 0


def verify(path: Path, wanted: list[str]) -> None:
    """Fail loudly unless every requested icon still resolves in the output.

    Worth its own step because the failure it catches is silent: a subset
    that keeps the icon *glyphs* but loses the ligature *rules* passes every
    size check, loads without error, and then renders "expand_more" as the
    word "expand_more" in the running UI. That is exactly what the wrong
    feature tag produced the first time this script was written.
    """
    from fontTools.ttLib import TTFont

    subset = TTFont(path)
    surviving = build_ligature_map(subset)
    missing = [name for name in wanted if name not in surviving]
    if missing:
        raise SystemExit(
            f"Subset kept the glyphs but lost the ligature rules for: "
            f"{', '.join(missing[:10])}"
            + ("…" if len(missing) > 10 else "")
        )

    # Extra *names* are fine and cost nothing when they are upstream
    # aliases resolving to a glyph we already keep (``radio_button_off``
    # for ``radio_button_unchecked``, say). Extra *glyphs* are not: that
    # would mean layout closure leaked real icons back in.
    kept_glyphs = {surviving[name] for name in wanted}
    leaked = {
        name: glyph
        for name, glyph in surviving.items()
        if glyph not in kept_glyphs
    }
    if leaked:
        raise SystemExit(
            f"Subset leaked {len(leaked)} unrequested icon glyphs "
            f"(e.g. {sorted(leaked)[:5]}) — layout closure is back on?"
        )


if __name__ == "__main__":
    raise SystemExit(main())
