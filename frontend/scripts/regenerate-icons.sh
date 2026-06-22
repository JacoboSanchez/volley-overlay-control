#!/usr/bin/env bash
# Regenerate the raster PWA icons from public/icon.svg.
#
# The SVG is the source of truth; the PNG siblings (used by Chrome for the
# installed-app launcher icon, and by iOS for the home-screen icon) must be
# re-rasterised whenever icon.svg changes. This needs a rasteriser on PATH —
# rsvg-convert (librsvg), Inkscape, or ImageMagick — none of which is required
# at build time, so this is a manual/CI step rather than part of `npm run build`.
#
# Usage:  frontend/scripts/regenerate-icons.sh
set -euo pipefail

cd "$(dirname "$0")/.."
SRC="public/icon.svg"
[ -f "$SRC" ] || { echo "Missing $SRC" >&2; exit 1; }

render() { # size output
  local size="$1" out="$2"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "$size" -h "$size" "$SRC" -o "$out"
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "$SRC" -w "$size" -h "$size" -o "$out" >/dev/null 2>&1
  elif command -v magick >/dev/null 2>&1; then
    magick -background none "$SRC" -resize "${size}x${size}" "$out"
  elif command -v convert >/dev/null 2>&1; then
    convert -background none "$SRC" -resize "${size}x${size}" "$out"
  else
    echo "No rasteriser found. Install one of: librsvg (rsvg-convert), inkscape, imagemagick." >&2
    exit 1
  fi
}

render 192 public/icon-192x192.png
render 512 public/icon-512x512.png
render 180 public/apple-touch-icon.png
echo "Regenerated icon-192x192.png, icon-512x512.png, apple-touch-icon.png from $SRC"
