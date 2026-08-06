import { useCallback, useRef, useState } from 'react';
import { ApiError } from '../api/http';

export interface UseAsyncActionOptions {
  /** Turn a thrown value into the message stored in `error`. */
  formatError?: (err: unknown) => string;
  /**
   * Called with the formatted message (and the raw throwable) after a failed
   * run. Use it to route the failure somewhere the caller already renders — a
   * toast, a page-level banner — instead of reading `error` locally.
   */
  onError?: (message: string, err: unknown) => void;
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
 * The message an API failure should show: the backend's own `detail` when the
 * throwable is an {@link ApiError}, otherwise the caller's fallback copy.
 *
 * This is the "ApiError detail, else a translated fallback" ternary that every
 * page action used to spell out by hand.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

/** {@link apiErrorMessage} pre-bound to a fallback, for `formatError`. */
export function formatApiError(fallback: string): (err: unknown) => string {
  return (err) => apiErrorMessage(err, fallback);
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
  const optsRef = useRef<UseAsyncActionOptions | undefined>(options);
  optsRef.current = options;

  const run = useCallback(async (...args: T) => {
    setPending(true);
    setError(null);
    try {
      await fnRef.current(...args);
    } catch (e) {
      const opts = optsRef.current;
      const message = (opts?.formatError ?? defaultFormatError)(e);
      setError(message);
      opts?.onError?.(message, e);
    } finally {
      setPending(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);

  return { run, pending, error, clearError };
}

export interface RunOptions {
  /** Message to show when the throwable is not an {@link ApiError}. */
  fallback: string;
  /** Ran after a failure, before `pending` clears — e.g. to re-sync a toggle
   *  whose optimistic label no longer matches the server. */
  onFailure?: () => void | Promise<void>;
}

export interface AsyncRunner {
  /**
   * Run `fn` behind the shared `pending` flag. A failure lands in `error`
   * (the {@link ApiError} detail, else `options.fallback`).
   */
  run: (fn: () => Promise<void>, options: RunOptions) => Promise<void>;
  pending: boolean;
  error: string | null;
  setError: (message: string) => void;
  clearError: () => void;
}

/**
 * One `pending` flag and one `error` slot shared by a screen's whole set of
 * actions — the shape of every account page, which disables its buttons while
 * any one row action is in flight and renders a single error banner.
 *
 * Unlike {@link useAsyncAction}, the callback is supplied per call rather than
 * per hook, so a page needs one runner instead of one hook per action.
 */
export function useAsyncRunner(): AsyncRunner {
  const [pending, setPending] = useState(false);
  const [error, setErrorState] = useState<string | null>(null);

  const run = useCallback(async (fn: () => Promise<void>, options: RunOptions) => {
    setPending(true);
    setErrorState(null);
    try {
      await fn();
    } catch (e) {
      setErrorState(apiErrorMessage(e, options.fallback));
      await options.onFailure?.();
    } finally {
      setPending(false);
    }
  }, []);

  const setError = useCallback((message: string) => setErrorState(message), []);
  const clearError = useCallback(() => setErrorState(null), []);

  return { run, pending, error, setError, clearError };
}
