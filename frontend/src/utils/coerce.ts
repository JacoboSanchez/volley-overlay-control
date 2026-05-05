export function toNumber(v: unknown): number {
  return typeof v === 'number' ? v : typeof v === 'string' ? Number(v) || 0 : 0;
}

export function asString(v: unknown): string | null;
export function asString(v: unknown, fallback: string): string;
export function asString(v: unknown, fallback?: string): string | null {
  if (typeof v !== 'string') return fallback ?? null;
  if (fallback === undefined) return v ? v : null;
  return v;
}

export function asColor(v: unknown, fallback: string): string {
  return typeof v === 'string' && v ? v : fallback;
}

export function asBool(v: unknown, fallback = false): boolean {
  if (typeof v === 'boolean') return v;
  if (v === 'true') return true;
  if (v === 'false') return false;
  return fallback;
}
