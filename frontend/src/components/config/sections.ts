/** The config panel's section registry.
 *
 *  One array replaces what used to be four parallel structures (a union type,
 *  an ordering array, a label-key record and an icon record) that every new
 *  section had to be added to in lockstep.
 */
export interface ConfigSectionDef {
  id: string;
  /** i18n key for the section's label. */
  labelKey: string;
  /** Material Icons ligature shown beside the label. */
  icon: string;
}

// ``presets`` sits at the top so the operator notices the
// saved-configuration entry point before drilling into individual
// fields. Both env-driven ``APP_THEMES`` entries and operator-saved
// presets live in that single section.
export const CONFIG_SECTIONS = [
  { id: 'presets', labelKey: 'section.presets', icon: 'bookmarks' },
  { id: 'teams', labelKey: 'section.teams', icon: 'groups' },
  { id: 'overlay', labelKey: 'section.overlay', icon: 'palette' },
  { id: 'position', labelKey: 'section.position', icon: 'open_with' },
  { id: 'buttons', labelKey: 'section.buttons', icon: 'touch_app' },
  { id: 'rules', labelKey: 'section.rules', icon: 'rule' },
  { id: 'display', labelKey: 'section.display', icon: 'visibility' },
  { id: 'stats', labelKey: 'section.stats', icon: 'query_stats' },
  { id: 'recap', labelKey: 'section.recap', icon: 'summarize' },
  { id: 'general', labelKey: 'section.general', icon: 'settings' },
  { id: 'links', labelKey: 'section.links', icon: 'link' },
] as const satisfies readonly ConfigSectionDef[];

export type SectionId = (typeof CONFIG_SECTIONS)[number]['id'];
