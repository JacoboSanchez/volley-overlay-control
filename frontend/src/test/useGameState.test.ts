import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useGameState } from '../hooks/useGameState';
import * as api from '../api/client';
import * as ws from '../api/websocket';

vi.mock('../api/client', () => ({
  initSession: vi.fn(),
  getCustomization: vi.fn(),
  addPoint: vi.fn(),
  addSet: vi.fn(),
  addTimeout: vi.fn(),
  changeServe: vi.fn(),
  setScore: vi.fn(),
  setSets: vi.fn(),
  resetGame: vi.fn(),
  setVisibility: vi.fn(),
  setSimpleMode: vi.fn(),
  undoLast: vi.fn(),
}));

vi.mock('../api/websocket', () => ({
  createWebSocket: vi.fn(),
}));

import type { GameState } from '../api/client';

const mockState = {
  team_1: { sets: 0, scores: { set_1: 0 } },
  team_2: { sets: 0, scores: { set_1: 0 } },
  visible: true,
  simple_mode: false,
} as unknown as GameState;

const mockCustomization = { 'Team 1 Name': 'Home' };

interface MockWs {
  close: ReturnType<typeof vi.fn>;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
}

describe('useGameState', () => {
  let mockWs: MockWs;

  beforeEach(() => {
    vi.clearAllMocks();
    mockWs = { close: vi.fn(), onclose: null, onerror: null };
    vi.mocked(ws.createWebSocket).mockReturnValue(mockWs as unknown as WebSocket);
    vi.mocked(api.initSession).mockResolvedValue({ success: true, state: mockState });
    vi.mocked(api.getCustomization).mockResolvedValue(mockCustomization);
  });

  it('returns initial null state', () => {
    const { result } = renderHook(() => useGameState(''));
    expect(result.current.state).toBeNull();
    expect(result.current.customization).toBeNull();
    expect(result.current.connected).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('initialize sets state and customization on success', async () => {
    const { result } = renderHook(() => useGameState('test-oid'));

    await act(async () => {
      await result.current.initialize();
    });

    expect(api.initSession).toHaveBeenCalledWith('test-oid');
    expect(api.getCustomization).toHaveBeenCalledWith('test-oid');
    expect(result.current.state).toEqual(mockState);
    expect(result.current.customization).toEqual(mockCustomization);
  });

  it('initialize sets error on failure', async () => {
    vi.mocked(api.initSession).mockResolvedValue({ success: false, message: 'bad oid' });
    const { result } = renderHook(() => useGameState('bad'));

    await act(async () => {
      await result.current.initialize();
    });

    expect(result.current.error).toBe('bad oid');
    expect(result.current.state).toBeNull();
  });

  it('initialize sets error on exception', async () => {
    vi.mocked(api.initSession).mockRejectedValue(new Error('network error'));
    const { result } = renderHook(() => useGameState('fail'));

    await act(async () => {
      await result.current.initialize();
    });

    expect(result.current.error).toBe('network error');
  });

  it('initialize with no oid resets state', async () => {
    const { result } = renderHook(() => useGameState(''));

    await act(async () => {
      await result.current.initialize();
    });

    expect(result.current.state).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('initialize connects WebSocket after success', async () => {
    const { result } = renderHook(() => useGameState('ws-oid'));

    await act(async () => {
      await result.current.initialize();
    });

    expect(ws.createWebSocket).toHaveBeenCalledWith('ws-oid', expect.any(Object));
  });

  it('addPoint action updates state on success', async () => {
    const updatedState = { ...mockState, team_1: { ...mockState.team_1, scores: { set_1: 1 } } };
    vi.mocked(api.addPoint).mockResolvedValue({ success: true, state: updatedState });

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.addPoint(1);
    });

    expect(api.addPoint).toHaveBeenCalledWith('oid', 1, false);
    expect(result.current.state).toEqual(updatedState);
  });

  it('addPoint with undo passes undo flag', async () => {
    vi.mocked(api.addPoint).mockResolvedValue({ success: true, state: mockState });
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.addPoint(2, true);
    });

    expect(api.addPoint).toHaveBeenCalledWith('oid', 2, true);
  });

  it('action sets error on exception', async () => {
    vi.mocked(api.addPoint).mockRejectedValue(new Error('action failed'));
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      const res = await result.current.actions.addPoint(1);
      expect(res.success).toBe(false);
    });

    expect(result.current.error).toBe('action failed');
  });

  it('reset action calls api.resetGame', async () => {
    vi.mocked(api.resetGame).mockResolvedValue({ success: true, state: mockState });
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.reset();
    });

    expect(api.resetGame).toHaveBeenCalledWith('oid');
  });

  it('undoLast action calls api.undoLast', async () => {
    vi.mocked(api.undoLast).mockResolvedValue({ success: true, state: mockState });
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.undoLast();
    });

    expect(api.undoLast).toHaveBeenCalledWith('oid');
  });

  it('setVisibility action calls api', async () => {
    vi.mocked(api.setVisibility).mockResolvedValue({ success: true, state: mockState });
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.setVisibility(false);
    });

    expect(api.setVisibility).toHaveBeenCalledWith('oid', false);
  });

  it('refreshCustomization fetches new customization without re-init', async () => {
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    // Clear call counts from initialize() so we can assert only on refresh calls
    vi.clearAllMocks();
    vi.mocked(api.getCustomization).mockResolvedValue({ 'Team 1 Name': 'Updated' });

    await act(async () => {
      await result.current.refreshCustomization();
    });

    // Should fetch fresh customization…
    expect(api.getCustomization).toHaveBeenCalledWith('oid');
    expect(result.current.customization).toEqual({ 'Team 1 Name': 'Updated' });

    // …but must NOT call initSession — that would overwrite the backend session
    // with potentially stale overlay data and revert the overlay on the next
    // game action (addPoint, etc.).
    expect(api.initSession).not.toHaveBeenCalled();
  });

  it('cleanup closes WebSocket on unmount', async () => {
    const { result, unmount } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    unmount();
    expect(mockWs.close).toHaveBeenCalled();
  });
});
