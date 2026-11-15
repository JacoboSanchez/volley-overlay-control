// ── Text-zoom guard ──────────────────────────────────────────────────
// A scoreboard is a broadcast graphic laid out on a fixed 1920×1080
// canvas, so its type must not follow the viewer's reading preferences.
// Android apps that composite the overlay through a system WebView
// (PRISM Live Studio and similar) inherit the phone's "font size"
// accessibility setting as a WebView *text zoom*: every font size is
// multiplied by it while boxes keep their size, so scores overflow.
//
// There is no CSS opt-out for that text zoom (``text-size-adjust`` only
// covers the other mechanism, Chrome's text autosizer, and is set here
// too). So this script measures the factor with a probe and, when there
// is one, rewrites the loaded stylesheets to cancel it:
//
//   * absolute font sizes (px, cqw, clamp(), var()…) are divided by it;
//   * the root font size is divided by it, which corrects rem font sizes
//     and everything that inherits the default;
//   * absolute line-heights are divided by it (text zoom scales those);
//   * em/rem lengths elsewhere (letter-spacing, padding…) are multiplied
//     by it, because they resolve against the now-smaller declared size.
//
// Loaded from base.html after the last stylesheet, before app.js. Scripts
// that size text inline divide by ``window.OVERLAY_TEXT_ZOOM``.
(function () {
  window.OVERLAY_TEXT_ZOOM = 1;

  const root = document.documentElement;

  // Chrome's autosizer path (font scale via text autosizing).
  const base = document.createElement("style");
  base.textContent =
    "html{-webkit-text-size-adjust:none;text-size-adjust:none}";
  document.head.insertBefore(base, document.head.firstChild);

  // Probe: a 100px font with line-height 1 lays out 100px tall unless
  // something scales text behind the page's back.
  const probe = document.createElement("div");
  probe.id = "overlay-text-zoom-probe";
  probe.textContent = "0";
  probe.style.cssText =
    "position:absolute;left:-9999px;top:0;visibility:hidden;margin:0;" +
    "padding:0;border:0;white-space:nowrap;font:normal 100px/1 sans-serif";
  root.appendChild(probe);
  const factor = probe.getBoundingClientRect().height / 100;
  probe.remove();

  // Ignore measurement noise and implausible readings.
  if (!(factor > 0.3 && factor < 4) || Math.abs(factor - 1) < 0.02) return;
  window.OVERLAY_TEXT_ZOOM = factor;
  root.dataset.textZoom = factor.toFixed(3);

  const RELATIVE = /(\d|\.)(r?em|%)(?![a-z])/i; // sizes that follow a parent
  const HAS_LENGTH = /\d[a-z]|\(/i; // a unit or a function, not a keyword
  const EM_LENGTH = /(-?(?:\d+\.?\d*|\.\d+))(r?em)(?![a-z])/gi;
  const divide = (value) => `calc((${value}) / ${factor})`;

  // Split a declaration value on top-level whitespace (not inside
  // parentheses), keeping the separators so it can be rejoined verbatim.
  function splitTopLevel(value) {
    const parts = [];
    let depth = 0;
    let current = "";
    for (const ch of value) {
      if (ch === "(") depth += 1;
      else if (ch === ")") depth -= 1;
      if (depth === 0 && /\s/.test(ch)) {
        if (current) parts.push(current);
        parts.push(ch);
        current = "";
      } else {
        current += ch;
      }
    }
    if (current) parts.push(current);
    return parts;
  }

  // ``font`` shorthand: the size is the first component that carries a
  // unit or is a function (weights are bare numbers), optionally glued to
  // ``/line-height``. Returns null when there is nothing to rewrite.
  function fixFontShorthand(value) {
    const parts = splitTopLevel(value);
    for (let i = 0; i < parts.length; i += 1) {
      const token = parts[i];
      if (!token.trim() || token === "/") continue;
      let depth = 0;
      let slash = -1;
      for (let j = 0; j < token.length; j += 1) {
        if (token[j] === "(") depth += 1;
        else if (token[j] === ")") depth -= 1;
        else if (token[j] === "/" && depth === 0) {
          slash = j;
          break;
        }
      }
      const size = slash === -1 ? token : token.slice(0, slash);
      if (!/^(\.?\d|[a-z-]+\()/i.test(size) || /^\d+\.?\d*$/.test(size)) {
        continue;
      }
      if (RELATIVE.test(size)) return null;
      parts[i] = divide(size) + (slash === -1 ? "" : token.slice(slash));
      return parts.join("");
    }
    return null;
  }

  function fixStyle(style) {
    const names = Array.from(style);
    const set = (name, value) =>
      style.setProperty(name, value, style.getPropertyPriority(name));

    const shorthand = style.getPropertyValue("font");
    const fixedShorthand = shorthand && fixFontShorthand(shorthand);
    if (fixedShorthand) {
      style.setProperty(
        "font",
        fixedShorthand,
        style.getPropertyPriority("font-size"),
      );
    } else {
      const size = style.getPropertyValue("font-size");
      if (size && HAS_LENGTH.test(size) && !RELATIVE.test(size)) {
        set("font-size", divide(size));
      }
    }

    const lineHeight = style.getPropertyValue("line-height");
    if (
      !fixedShorthand &&
      lineHeight &&
      /\d[a-z]/i.test(lineHeight) &&
      !RELATIVE.test(lineHeight)
    ) {
      set("line-height", divide(lineHeight));
    }

    for (const name of names) {
      if (name.startsWith("--") || name.startsWith("font")) continue;
      if (name === "line-height") continue;
      const value = style.getPropertyValue(name);
      if (!value || !/em(?![a-z])/i.test(value)) continue;
      const next = value.replace(EM_LENGTH, `calc($1$2 * ${factor})`);
      if (next !== value) set(name, next);
    }
  }

  function fixSheet(sheet) {
    let rules;
    try {
      rules = sheet.cssRules;
    } catch {
      // Cross-origin sheet (web fonts): only @font-face rules, nothing to fix.
      return;
    }
    fixRules(rules);
  }

  function fixRules(rules) {
    for (const rule of Array.from(rules)) {
      if (rule instanceof CSSFontFaceRule) continue;
      if (rule instanceof CSSImportRule) {
        if (rule.styleSheet) fixSheet(rule.styleSheet);
        continue;
      }
      if (rule.style) fixStyle(rule.style);
      if (rule.cssRules) fixRules(rule.cssRules);
    }
  }

  for (const sheet of Array.from(document.styleSheets)) {
    if (sheet.ownerNode !== base) fixSheet(sheet);
  }

  // Root size last and lowest in the cascade, so a style's own (already
  // corrected) html/:root font size still wins.
  base.textContent += `html{font-size:calc(1rem / ${factor})}`;
})();
