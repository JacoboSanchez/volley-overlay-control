/**
 * Every Material Icons ligature the control UI renders.
 *
 * This list is the input to the font subset shipped in
 * ``public/fonts/material-icons-subset.woff2`` (regenerate with
 * ``python3 scripts/icons/build_font_subset.py``). The upstream font carries
 * ~2,200 icons at 125 kB; we use a few dozen, and the subset is a fraction
 * of that on every first paint.
 *
 * **Adding an icon means adding it here.** An icon missing from this list
 * renders as a blank box in production, so ``icons.test.ts`` scans the
 * source for ``material-icons`` usages and fails the build if any name is
 * unlisted — the mistake surfaces in CI rather than on an operator's
 * screen mid-match.
 *
 * Names that reach the DOM through a lookup table or a helper (config
 * section icons, match-alert triangles, theme toggle, preset categories)
 * cannot be found by scanning JSX children, so they are grouped separately
 * below and the test resolves them from the same tables.
 */

/** Icons written literally as a ``<span className="material-icons">`` child. */
export const LITERAL_ICONS = [
  'add',
  'arrow_back',
  'bolt',
  'broken_image',
  'calendar_month',
  'change_circle',
  'check',
  'check_circle',
  'chevron_left',
  'chevron_right',
  'close',
  'cloud_off',
  'cloud_upload',
  'content_copy',
  'dark_mode',
  'dashboard',
  'delete',
  'description',
  'done',
  'download',
  'edit',
  'error_outline',
  'expand_less',
  'expand_more',
  'fullscreen',
  'fullscreen_exit',
  'grid_on',
  'history',
  'hourglass_top',
  'image',
  'light_mode',
  'logout',
  'more_vert',
  'open_in_new',
  'play_arrow',
  'podcasts',
  'radio_button_unchecked',
  'refresh',
  'remove',
  'restart_alt',
  'save',
  'settings',
  'share',
  'sports_esports',
  'sports_tennis',
  'sports_volleyball',
  'summarize',
  'swap_horiz',
  'sync',
  'timer',
  'tv',
  'tv_off',
  'undo',
  'verified',
  'visibility',
  'visibility_off',
  'warning',
  'window',
] as const;

/**
 * Icons chosen at runtime from a table or helper. Each entry names where
 * it comes from so the list can be checked against the source it mirrors.
 */
export const DYNAMIC_ICONS = [
  // ConfigPanel SECTION_ICONS
  'bookmarks',
  'groups',
  'palette',
  'open_with',
  'touch_app',
  'rule',
  'query_stats',
  'link',
  // ConfigPanel themeIcon
  'brightness_auto',
  // MatchRulesSection MODE_ICONS
  'beach_access',
  // PresetPicker CATEGORY_ICON (+ its 'tune' fallback)
  'badge',
  'view_quilt',
  'tune',
  // MatchAlertIndicator SIDE_TRIANGLE + the match-finished trophy
  'arrow_drop_up',
  'arrow_drop_down',
  'arrow_left',
  'arrow_right',
  'emoji_events',
] as const;

/** The full set the font subset must contain. */
export const USED_ICONS: readonly string[] = [
  ...new Set<string>([...LITERAL_ICONS, ...DYNAMIC_ICONS]),
].sort();
