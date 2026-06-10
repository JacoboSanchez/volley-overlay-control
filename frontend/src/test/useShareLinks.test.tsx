import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useShareLinks } from '../hooks/useShareLinks';
import * as api from '../api/client';

vi.mock('../api/client', () => ({
  getLinks: vi.fn(),
}));

describe('useShareLinks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getLinks).mockResolvedValue({
      control: 'https://x/control',
      overlay: 'https://x/overlay',
      preview: 'https://x/preview',
      follow: 'https://x/follow',
    });
  });

  it('starts closed with no links and no fetch', () => {
    const { result } = renderHook(() => useShareLinks('my-oid'));
    expect(result.current.shareOpen).toBe(false);
    expect(result.current.shareLinks).toBeNull();
    expect(api.getLinks).not.toHaveBeenCalled();
  });

  it('opens and populates the links on success', async () => {
    const { result } = renderHook(() => useShareLinks('my-oid'));
    await act(async () => {
      await result.current.handleOpenShare();
    });
    expect(result.current.shareOpen).toBe(true);
    expect(api.getLinks).toHaveBeenCalledWith('my-oid');
    expect(result.current.shareLinks).toEqual({
      control: 'https://x/control',
      overlay: 'https://x/overlay',
      preview: 'https://x/preview',
      follow: 'https://x/follow',
    });
  });

  it('coerces non-string link fields to empty strings', async () => {
    vi.mocked(api.getLinks).mockResolvedValue({
      control: 'https://x/control',
      overlay: 42,
      preview: null,
    });
    const { result } = renderHook(() => useShareLinks('my-oid'));
    await act(async () => {
      await result.current.handleOpenShare();
    });
    expect(result.current.shareLinks).toEqual({
      control: 'https://x/control',
      overlay: '',
      preview: '',
      follow: '',
    });
  });

  it('falls back to an empty links object when the fetch fails', async () => {
    vi.mocked(api.getLinks).mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useShareLinks('my-oid'));
    await act(async () => {
      await result.current.handleOpenShare();
    });
    expect(result.current.shareOpen).toBe(true);
    expect(result.current.shareLinks).toEqual({});
  });

  it('does not refetch on a second open once links are cached', async () => {
    const { result } = renderHook(() => useShareLinks('my-oid'));
    await act(async () => {
      await result.current.handleOpenShare();
    });
    act(() => {
      result.current.setShareOpen(false);
    });
    await act(async () => {
      await result.current.handleOpenShare();
    });
    expect(result.current.shareOpen).toBe(true);
    expect(api.getLinks).toHaveBeenCalledTimes(1);
  });

  it('is a no-op without an oid', async () => {
    const { result } = renderHook(() => useShareLinks(''));
    await act(async () => {
      await result.current.handleOpenShare();
    });
    expect(result.current.shareOpen).toBe(false);
    expect(api.getLinks).not.toHaveBeenCalled();
  });
});
