/**
 * Contrast helpers for adjusting team colors so they remain readable
 * on the current surface while preserving the team's hue.
 *
 * The strategy is: keep the original hue and saturation, and only nudge
 * the HSL lightness toward the side that increases contrast against the
 * background until the WCAG AA threshold (4.5:1 for normal text) is met.
 * If the surface itself is mid-grey or the color cannot reach the target
 * without losing all chroma, the best-effort value is returned.
 */

const WCAG_AA_NORMAL = 4.5;

export interface Rgb {
  r: number;
  g: number;
  b: number;
}

export function parseHexColor(hex: string): Rgb | null {
  if (typeof hex !== 'string') return null;
  let s = hex.trim().replace(/^#/, '');
  if (s.length === 3) {
    s = s.split('').map((c) => c + c).join('');
  }
  if (s.length !== 6 || !/^[0-9a-fA-F]{6}$/.test(s)) return null;
  return {
    r: parseInt(s.slice(0, 2), 16),
    g: parseInt(s.slice(2, 4), 16),
    b: parseInt(s.slice(4, 6), 16),
  };
}

function toHex2(n: number): string {
  const clamped = Math.max(0, Math.min(255, Math.round(n)));
  return clamped.toString(16).padStart(2, '0');
}

export function rgbToHex({ r, g, b }: Rgb): string {
  return `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`;
}

function channelLuminance(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function relativeLuminance({ r, g, b }: Rgb): number {
  return (
    0.2126 * channelLuminance(r) +
    0.7152 * channelLuminance(g) +
    0.0722 * channelLuminance(b)
  );
}

export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

export interface Hsl {
  h: number;
  s: number;
  l: number;
}

export function rgbToHsl({ r, g, b }: Rgb): Hsl {
  const r1 = r / 255;
  const g1 = g / 255;
  const b1 = b / 255;
  const max = Math.max(r1, g1, b1);
  const min = Math.min(r1, g1, b1);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r1:
        h = (g1 - b1) / d + (g1 < b1 ? 6 : 0);
        break;
      case g1:
        h = (b1 - r1) / d + 2;
        break;
      default:
        h = (r1 - g1) / d + 4;
    }
    h *= 60;
  }
  return { h, s, l };
}

function hueToRgb(p: number, q: number, t: number): number {
  let tt = t;
  if (tt < 0) tt += 1;
  if (tt > 1) tt -= 1;
  if (tt < 1 / 6) return p + (q - p) * 6 * tt;
  if (tt < 1 / 2) return q;
  if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
  return p;
}

export function hslToRgb({ h, s, l }: Hsl): Rgb {
  const hn = ((h % 360) + 360) % 360 / 360;
  if (s === 0) {
    const v = Math.round(l * 255);
    return { r: v, g: v, b: v };
  }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return {
    r: Math.round(hueToRgb(p, q, hn + 1 / 3) * 255),
    g: Math.round(hueToRgb(p, q, hn) * 255),
    b: Math.round(hueToRgb(p, q, hn - 1 / 3) * 255),
  };
}

/**
 * Return a version of ``fg`` that meets ``minRatio`` contrast against
 * ``bg`` by shifting only the HSL lightness. Hue and saturation are
 * preserved so the team identity stays recognisable. If the threshold
 * cannot be reached (e.g. the surface is mid-grey), the closest
 * approximation is returned.
 */
export function getReadableOnSurface(
  fg: string,
  bg: string,
  minRatio: number = WCAG_AA_NORMAL,
): string {
  const fgRgb = parseHexColor(fg);
  const bgRgb = parseHexColor(bg);
  if (!fgRgb || !bgRgb) return fg;

  if (contrastRatio(fgRgb, bgRgb) >= minRatio) return fg;

  const bgLum = relativeLuminance(bgRgb);
  const hsl = rgbToHsl(fgRgb);
  // If the surface is dark, lifting lightness raises contrast; if it is
  // light, lowering lightness does. Mid-grey surfaces are ambiguous —
  // pick the direction with more headroom.
  const goLighter = bgLum < 0.5 ? true : bgLum > 0.5 ? false : hsl.l < 0.5;

  let lo = hsl.l;
  let hi = goLighter ? 1 : 0;
  let best: Rgb = fgRgb;
  let bestRatio = contrastRatio(fgRgb, bgRgb);

  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) / 2;
    const candidate = hslToRgb({ h: hsl.h, s: hsl.s, l: mid });
    const ratio = contrastRatio(candidate, bgRgb);
    if (ratio >= bestRatio) {
      best = candidate;
      bestRatio = ratio;
    }
    if (ratio >= minRatio) {
      // Try to come back closer to the original lightness while still
      // meeting the threshold, so the team identity drifts as little as
      // possible.
      hi = mid;
    } else {
      lo = mid;
    }
  }

  // Final pick: prefer the lightness closest to the original that still
  // clears ``minRatio``. ``hi`` is that boundary after the search.
  const finalCandidate = hslToRgb({ h: hsl.h, s: hsl.s, l: hi });
  if (contrastRatio(finalCandidate, bgRgb) >= minRatio) {
    return rgbToHex(finalCandidate);
  }
  return rgbToHex(best);
}
