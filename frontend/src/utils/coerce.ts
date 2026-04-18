export function toNumber(v: unknown): number {
  return typeof v === 'number' ? v : typeof v === 'string' ? Number(v) || 0 : 0;
}

export function asString(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}
