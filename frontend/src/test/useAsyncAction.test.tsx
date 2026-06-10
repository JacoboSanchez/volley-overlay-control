import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAsyncAction } from '../hooks/useAsyncAction';

function deferred() {
  let resolve!: () => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<void>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useAsyncAction', () => {
  it('tracks pending across a successful run', async () => {
    const d = deferred();
    const fn = vi.fn(() => d.promise);
    const { result } = renderHook(() => useAsyncAction(fn));

    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run();
    });
    expect(result.current.pending).toBe(true);

    await act(async () => {
      d.resolve();
      await runPromise;
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fn).toHaveBeenCalledOnce();
  });

  it('forwards arguments to the wrapped function', async () => {
    const fn = vi.fn(async (_team: number, _label: string) => {});
    const { result } = renderHook(() => useAsyncAction(fn));
    await act(async () => {
      await result.current.run(2, 'timeout');
    });
    expect(fn).toHaveBeenCalledWith(2, 'timeout');
  });

  it('captures the error message on rejection and clears pending', async () => {
    const { result } = renderHook(() =>
      useAsyncAction(async () => {
        throw new Error('server exploded');
      }),
    );
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe('server exploded');
  });

  it('stringifies non-Error throwables by default', async () => {
    const { result } = renderHook(() =>
      useAsyncAction(async () => {
        throw 'plain string failure';
      }),
    );
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBe('plain string failure');
  });

  it('uses the custom formatError when provided', async () => {
    const { result } = renderHook(() =>
      useAsyncAction(
        async () => {
          throw new Error('raw');
        },
        { formatError: (err) => `friendly: ${(err as Error).message}` },
      ),
    );
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBe('friendly: raw');
  });

  it('clears a previous error when a new run starts, and via clearError', async () => {
    const d = deferred();
    let fail = true;
    const { result } = renderHook(() =>
      useAsyncAction(async () => {
        if (fail) throw new Error('first failure');
        return d.promise;
      }),
    );
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBe('first failure');

    // clearError resets without running anything.
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();

    // Error from a previous run is wiped as soon as the next run starts.
    await act(async () => {
      await result.current.run();
    });
    expect(result.current.error).toBe('first failure');
    fail = false;
    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run();
    });
    expect(result.current.error).toBeNull();
    await act(async () => {
      d.resolve();
      await runPromise;
    });
    expect(result.current.error).toBeNull();
  });

  it('keeps a stable run identity while always invoking the latest fn', async () => {
    const first = vi.fn(async () => {});
    const second = vi.fn(async () => {});
    const { result, rerender } = renderHook(({ fn }) => useAsyncAction(fn), {
      initialProps: { fn: first },
    });
    const initialRun = result.current.run;
    rerender({ fn: second });
    expect(result.current.run).toBe(initialRun);
    await act(async () => {
      await result.current.run();
    });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });
});
