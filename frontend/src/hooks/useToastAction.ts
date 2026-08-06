import { useToast } from '../components/Toast';
import { formatApiError, useAsyncAction, type UseAsyncActionResult } from './useAsyncAction';

/**
 * {@link useAsyncAction} for the account pages' dominant shape: a single
 * action whose failure is announced with an error toast rather than an inline
 * banner, showing the API's own `detail` when there is one and `fallback`
 * otherwise.
 *
 * `pending` still drives the button's disabled/spinner state; `error` is
 * available for callers that also want the message inline.
 */
export function useToastAction<T extends unknown[]>(
  fn: (...args: T) => Promise<void>,
  fallback: string,
): UseAsyncActionResult<T> {
  const { toast } = useToast();
  return useAsyncAction(fn, {
    formatError: formatApiError(fallback),
    onError: (message) => toast(message, 'error'),
  });
}
