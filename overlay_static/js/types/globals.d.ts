/**
 * Globals the overlay scripts share with their Jinja templates.
 *
 * The overlay JS is plain, non-module browser script: templates define a
 * few constants before loading it (overlay_templates/base.html,
 * _spectator.html, mosaic.html) and the scripts publish small APIs on
 * ``window`` for each other. Declaring them here is what lets
 * ``npm run typecheck:overlays`` check the scripts against the overlay
 * state contract (./overlay-state.d.ts, generated from
 * app/overlay/payload_schema.py) instead of failing on every global.
 */

import type { components } from "./overlay-state";

declare global {
  /** The document ``/ws/{public_token}`` sends; see overlay-state.schema.json. */
  type OverlayState = components["schemas"]["OverlayState"];

  /** GSAP, vendored as ``overlay_static/js/gsap.min.js`` (untyped here). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gsap: any;

  /** WebSocket URL built by base.html from its output key. */
  const wsUrl: string;

  interface Window {
    OVERLAY_STYLE?: string;
    OVERLAY_NATIVE_THEME?: string;
    OVERLAY_LOCALE?: string;
    OVERLAY_OUTPUT_KEY?: string;
    /**
     * Static demo state the style-preview / mosaic pages render instead of a
     * socket (app/overlay/style_preview.py). Intentionally partial: only the
     * fields a preview needs, so it is not the full contract.
     */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    OVERLAY_PREVIEW_STATE?: any;
    /** Shared label bundle from i18n_labels.js, keyed by locale then label. */
    OVERLAY_LABELS?: Record<string, Record<string, string>>;
    /** Set-summary recap API published by set_summary.js. */
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    SetSummary?: any;
  }
}

export {};
