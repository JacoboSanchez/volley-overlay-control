#!/usr/bin/env bash
# Regenerate the raster PWA icons from their SVG sources.
#
# The SVGs are the source of truth; the PNG siblings (used by Chrome for the
# installed-app launcher icon, and by iOS for the home-screen icon) must be
# re-rasterised whenever an SVG changes. This needs a rasteriser on PATH —
# rsvg-convert (librsvg), Inkscape, or ImageMagick — none of which is required
# at build time, so this is a manual/CI step rather than part of `npm run build`.
#
#   public/icon.svg        -> base app icon  (icon-192x192, icon-512x512,
#                                             apple-touch-icon)
#   public/icon-board.svg  -> scoreboard icon (icon-board-192x192,
#                                              icon-board-512x512)
#
# Usage:  frontend/scripts/regenerate-icons.sh
set -euo pipefail

cd "$(dirname "$0")/.."

render() { # src size output
  local src="$1" size="$2" out="$3"
  [ -f "$src" ] || { echo "Missing $src" >&2; exit 1; }
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "$size" -h "$size" "$src" -o "$out"
  elif command -v inkscape >/dev/null 2>&1; then
    inkscape "$src" -w "$size" -h "$size" -o "$out" >/dev/null 2>&1
  elif command -v magick >/dev/null 2>&1; then
    magick -background none "$src" -resize "${size}x${size}" "$out"
  elif command -v convert >/dev/null 2>&1; then
    convert -background none "$src" -resize "${size}x${size}" "$out"
  else
    echo "No rasteriser found. Install one of: librsvg (rsvg-convert), inkscape, imagemagick." >&2
    exit 1
  fi
}

# Base app icon.
render public/icon.svg 192 public/icon-192x192.png
render public/icon.svg 512 public/icon-512x512.png
render public/icon.svg 180 public/apple-touch-icon.png

# Scoreboard (per-board) icon.
render public/icon-board.svg 192 public/icon-board-192x192.png
render public/icon-board.svg 512 public/icon-board-512x512.png

echo "Regenerated base (icon-*) and board (icon-board-*) raster icons."
