/** Hosted icon library (team logos) — ``/api/v1/icons/*``.
 *
 *  Icons are stored server-side (resized + re-encoded to WebP) and served from
 *  the public /media mount; teams reference them by URL like any external logo.
 */

import { getPage, request, requestMultipart } from './http';

export interface IconOut {
  id: number;
  name: string;
  url: string;
  is_global: boolean;
  width: number;
  height: number;
  size_bytes: number;
}

export interface IconLibrary {
  globals: IconOut[];
  mine: IconOut[];
  quota: { used: number; limit: number };
}

export interface IconImportResult {
  team_id: number;
  team_name: string;
  status: 'ok' | 'skipped' | 'error';
  icon_id?: number | null;
  icon_url?: string | null;
  error?: string | null;
}

/** Multipart body shared by the personal and admin upload endpoints. */
export function iconForm(name: string, file: File): FormData {
  const form = new FormData();
  form.set('name', name);
  form.set('file', file);
  return form;
}

export async function listIcons(): Promise<IconLibrary> {
  // Only `globals` pages — it is the uncapped half of the library, and
  // X-Total-Count reports its size. `mine` and `quota` repeat identically on
  // every page (personal libraries are already capped by ICONS_MAX_PER_USER),
  // so they are taken from the first one.
  const first = await getPage<IconLibrary>('/icons', 0);
  const globals = [...first.body.globals];
  while (first.total >= 0 && globals.length < first.total) {
    // Advance by what the server actually returned, for the same reason
    // `getAllPages` does: the page size is the deployment's to choose.
    const next = await getPage<IconLibrary>('/icons', globals.length);
    if (!next.body.globals.length) break;
    globals.push(...next.body.globals);
  }
  return { ...first.body, globals };
}

export function uploadMyIcon(name: string, file: File): Promise<IconOut> {
  return requestMultipart<IconOut>('POST', '/icons/mine', iconForm(name, file));
}

export function renameMyIcon(id: number, name: string): Promise<IconOut> {
  return request<IconOut>('PATCH', `/icons/mine/${id}`, { name });
}

export function getMyIconUsage(id: number): Promise<{ teams: number }> {
  return request('GET', `/icons/mine/${id}/usage`);
}

export function deleteMyIcon(id: number): Promise<{ ok: boolean; teams_cleared: number }> {
  return request('DELETE', `/icons/mine/${id}`);
}

export function importIconsFromMyTeams(
  teamIds: number[],
): Promise<{ results: IconImportResult[] }> {
  return request('POST', '/icons/mine/import-from-teams', { team_ids: teamIds });
}
