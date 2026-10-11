import type { Translate } from '../i18n';

export type StyleCategory = 'compact' | 'broadcast' | 'jersey' | 'corners' | 'beach';
export type StyleKind = 'overlay' | 'summary';

export const OVERLAY_CATEGORIES: Record<string, StyleCategory> = {
  default: 'broadcast',
  original: 'broadcast',
  broadcast: 'broadcast',
  baseline: 'broadcast',
  ribbon: 'broadcast',
  split: 'broadcast',
  diagonal: 'broadcast',
  shield: 'broadcast',
  glass: 'broadcast',
  esports: 'broadcast',
  neon: 'broadcast',
  led: 'broadcast',
  compact: 'compact',
  micro: 'compact',
  pill: 'compact',
  vertical: 'compact',
  clear_jersey: 'jersey',
  neo_jersey: 'jersey',
  split_jersey: 'jersey',
  corner_jersey: 'jersey',
  corner_gradient: 'corners',
  corner_tags: 'corners',
  corner_wedge: 'corners',
  pylons: 'corners',
  pylons_gradient: 'corners',
  beach: 'beach',
  beach_twoline: 'beach',
};

export function stylePresentation(kind: StyleKind, id: string, t: Translate) {
  const key = `styleCatalog.${kind}.${id}`;
  const known = kind === 'summary' || Object.hasOwn(OVERLAY_CATEGORIES, id);
  return {
    id,
    name: known ? t(`${key}.name`) : id.replaceAll('_', ' '),
    description: known ? t(`${key}.description`) : t('stylePicker.customStyle'),
    category: OVERLAY_CATEGORIES[id] ?? 'broadcast',
    thumbnail: known ? `/static/img/style-previews/${kind}-${id}.webp` : null,
    known,
  };
}
