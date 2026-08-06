import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { ToastProvider } from '../components/Toast';
import { useToastAction } from '../hooks/useToastAction';
import { ApiError } from '../api/http';

function wrapper({ children }: { children: ReactNode }) {
  return <ToastProvider>{children}</ToastProvider>;
}

describe('useToastAction', () => {
  it('does not toast on success', async () => {
    const { result } = renderHook(() => useToastAction(async () => {}, 'could not save'), {
      wrapper,
    });
    await act(async () => {
      await result.current.run();
    });
    expect(document.querySelector('.acc-toast')).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('toasts the API detail as an error', async () => {
    const { result } = renderHook(
      () =>
        useToastAction(async () => {
          throw new ApiError(409, 'raw envelope', 'name already taken');
        }, 'could not save'),
      { wrapper },
    );
    await act(async () => {
      await result.current.run();
    });
    const toastEl = document.querySelector('.acc-toast');
    expect(toastEl).not.toBeNull();
    expect(toastEl).toHaveClass('error');
    expect(toastEl?.textContent).toBe('name already taken');
  });

  it('toasts the fallback for a non-API failure', async () => {
    const { result } = renderHook(
      () =>
        useToastAction(async () => {
          throw new Error('socket hang up');
        }, 'could not save'),
      { wrapper },
    );
    await act(async () => {
      await result.current.run();
    });
    expect(document.querySelector('.acc-toast')?.textContent).toBe('could not save');
  });

  it('tracks pending across the run', async () => {
    let resolve!: () => void;
    const promise = new Promise<void>((res) => {
      resolve = res;
    });
    const { result } = renderHook(() => useToastAction(() => promise, 'could not save'), {
      wrapper,
    });
    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run();
    });
    expect(result.current.pending).toBe(true);
    await act(async () => {
      resolve();
      await runPromise;
    });
    expect(result.current.pending).toBe(false);
  });

  it('forwards call arguments to the wrapped function', async () => {
    const fn = vi.fn(async (_id: number) => {});
    const { result } = renderHook(() => useToastAction(fn, 'could not save'), { wrapper });
    await act(async () => {
      await result.current.run(7);
    });
    expect(fn).toHaveBeenCalledWith(7);
  });
});
