/** Operator-saved and env-driven customization presets —
 *  ``/api/v1/customization/presets/*``.
 *
 *  Load is purely client-side: the React panel deep-merges ``values`` into its
 *  in-memory edit model and persists via the existing PUT /customization save
 *  flow. ``source`` is ``"system"`` for read-only entries derived from
 *  ``APP_THEMES`` and ``"user"`` for records the operator saved themselves.
 */

import { getAllPages, request } from './http';

export interface PresetCategory {
  id: 'team1_name' | 'team1_color' | 'team2_name' | 'team2_color' | 'position' | 'style';
}

export interface PresetSummary {
  slug: string;
  name: string;
  source: 'user' | 'global';
  is_active?: boolean;
  categories: string[];
  values: Record<string, unknown>;
}

export async function listPresets(): Promise<{ items: PresetSummary[] }> {
  const items = await getAllPages<{ items: PresetSummary[] }, PresetSummary>(
    '/customization/presets',
    (body) => body.items,
  );
  return { items };
}

export function createPreset(
  name: string,
  values: Record<string, unknown>,
): Promise<PresetSummary> {
  return request<PresetSummary>('POST', '/customization/presets', { name, values });
}

export function deletePreset(slug: string): Promise<void> {
  return request<void>('DELETE', `/customization/presets/${encodeURIComponent(slug)}`);
}
