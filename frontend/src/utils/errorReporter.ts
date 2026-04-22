/**
 * Forward uncaught errors and unhandled promise rejections to the backend
 * /api/v1/_log endpoint so they show up in the same log stream as server
 * errors. Uses navigator.sendBeacon when available so the browser does
 * not race a page-unload navigation against the network call.
 *
 * Idempotent: install() is a no-op on subsequent calls.
 */

const ENDPOINT = '/api/v1/_log';
const MAX_MESSAGE = 2000;
const MAX_STACK = 8000;
const DEDUPE_WINDOW_MS = 5000;
const STACK_HISTORY = 20;

let installed = false;

type ReportLevel = 'error' | 'warn';

interface RawReport {
  level: ReportLevel;
  message: string;
  stack?: string;
  oid?: string;
}

const recentSignatures = new Map<string, number>();

function dedupe(signature: string): boolean {
  const now = Date.now();
  for (const [sig, ts] of recentSignatures) {
    if (now - ts > DEDUPE_WINDOW_MS) recentSignatures.delete(sig);
  }
  if (recentSignatures.has(signature)) return true;
  recentSignatures.set(signature, now);
  if (recentSignatures.size > STACK_HISTORY) {
    const oldest = recentSignatures.keys().next().value;
    if (oldest !== undefined) recentSignatures.delete(oldest);
  }
  return false;
}

function readOidFromUrl(): string | undefined {
  const params = new URLSearchParams(window.location.search);
  return params.get('control') || params.get('oid') || undefined;
}

function safeStringify(value: unknown): string {
  try {
    return typeof value === 'string' ? value : JSON.stringify(value);
  } catch {
    return '[unserializable]';
  }
}

function buildPayload({ level, message, stack, oid }: RawReport): string {
  const body = {
    level,
    message: message.slice(0, MAX_MESSAGE),
    stack: stack ? stack.slice(0, MAX_STACK) : undefined,
    href: window.location.href,
    user_agent: navigator.userAgent,
    oid: oid ?? readOidFromUrl(),
  };
  return JSON.stringify(body);
}

export function reportClientError(report: RawReport): void {
  if (dedupe(`${report.level}|${report.message}`)) return;
  const body = buildPayload(report);
  try {
    if (typeof navigator.sendBeacon === 'function') {
      const blob = new Blob([body], { type: 'application/json' });
      if (navigator.sendBeacon(ENDPOINT, blob)) return;
    }
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // Reporting must never throw back into the page.
  }
}

export function installErrorReporter(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;

  window.addEventListener('error', (event: ErrorEvent) => {
    const err = event.error as Error | undefined;
    reportClientError({
      level: 'error',
      message: err?.message || event.message || 'Unknown error',
      stack: err?.stack,
    });
  });

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const message = reason instanceof Error ? reason.message : safeStringify(reason);
    reportClientError({
      level: 'error',
      message: `Unhandled rejection: ${message}`,
      stack: reason instanceof Error ? reason.stack : undefined,
    });
  });
}

/** Reset internal state. Test-only. */
export function _resetForTests(): void {
  installed = false;
  recentSignatures.clear();
}
