import { useCallback, useRef, useState } from 'react';

export interface UseAsyncActionOptions {
  formatError?: (err: unknown) => string;
}

export interface UseAsyncActionResult<T extends unknown[]> {
  run: (...args: T) => Promise<void>;
  pending: boolean;
  error: string | null;
  clearError: () => void;
}

function defaultFormatError(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/**
 * Wrap an async callback with the standard pending / error scaffolding
 * (`setPending(true) / try / catch / finally setPending(false)`).
 *
 * The returned `run` keeps a stable identity across renders; the latest
 * `fn` is invoked via a ref so callers don't need to memoise it.
 */
export function useAsyncAction<T extends unknown[]>(
  fn: (...args: T) => Promise<void>,
  options?: UseAsyncActionOptions,
): UseAsyncActionResult<T> {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const formatRef = useRef<((err: unknown) => string) | undefined>(options?.formatError);
  formatRef.current = options?.formatError;

  const run = useCallback(async (...args: T) => {
    setPending(true);
    setError(null);
    try {
      await fnRef.current(...args);
    } catch (e) {
      const fmt = formatRef.current ?? defaultFormatError;
      setError(fmt(e));
    } finally {
      setPending(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { run, pending, error, clearError };
}
