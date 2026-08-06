/** Per-user overlay CRUD — ``/api/v1/overlays/*``. */

import { getAllPages, request } from './http';

/** One of the caller's overlays (DB-backed, per-user). The ``oid`` is the
 *  overlay's name; ``description`` is an optional free-text subtitle. ``name``
 *  is a convenience label kept equal to the oid. */
export interface OverlayPayload {
  name: string;
  oid: string;
  description: string | null;
  public_token: string;
  output_url: string;
  control_token: string | null;
  control_url: string | null;
  public_control: boolean;
  public_control_url: string | null;
}

export interface OverlaySettings {
  description?: string | null;
  public_control?: boolean;
}

type OverlayRow = Omit<OverlayPayload, 'name'>;

function withName(r: OverlayRow): OverlayPayload {
  // The oid is the overlay's name; ``name`` is kept as a convenience alias.
  return { name: r.oid, ...r };
}

export async function getOverlays(): Promise<OverlayPayload[]> {
  const rows = await getAllPages<OverlayRow[], OverlayRow>('/overlays', (page) => page);
  return rows.map(withName);
}

export async function createOverlay(
  oid: string,
  settings: OverlaySettings = {},
): Promise<OverlayPayload> {
  const row = await request<OverlayRow>('POST', '/overlays', { oid, ...settings });
  return withName(row);
}

export async function updateOverlay(
  oid: string,
  settings: OverlaySettings,
): Promise<OverlayPayload> {
  const row = await request<OverlayRow>('PATCH', `/overlays/${encodeURIComponent(oid)}`, settings);
  return withName(row);
}

export function deleteOverlay(oid: string): Promise<void> {
  return request<void>('DELETE', `/overlays/${encodeURIComponent(oid)}`);
}

/** Mint a fresh control link for an overlay, revoking the previous one. */
export async function regenerateControlToken(oid: string): Promise<OverlayPayload> {
  const row = await request<OverlayRow>(
    'POST',
    `/overlays/${encodeURIComponent(oid)}/regenerate-control-token`,
    {},
  );
  return withName(row);
}
