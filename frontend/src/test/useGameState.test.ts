import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGameState } from '../hooks/useGameState';
import * as api from '../api/client';
import * as ws from '../api/websocket';

vi.mock('../api/client', () => {
  class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  }
  return {
    ApiError,
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
    startMatch: vi.fn(),
    getAudit: vi.fn(),
  };
});

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
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'ws-oid',
      count: 0,
      records: [],
      version: 1,
    });
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

  it('initialize surfaces the clean ApiError detail, not the raw message', async () => {
    vi.mocked(api.initSession).mockRejectedValue(
      new api.ApiError(
        403,
        'API POST /session/init failed (403): {"detail":"Invalid or revoked control link."}',
        'Invalid or revoked control link.',
      ),
    );
    const { result } = renderHook(() => useGameState('fail'));

    await act(async () => {
      await result.current.initialize();
    });

    expect(result.current.error).toBe('Invalid or revoked control link.');
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

  it('re-reads the audit log when the socket opens, including the first open', async () => {
    // The feed's mount fetch races the handshake: this socket does not
    // exist yet while that read is in flight, so an action from another
    // client in that window is broadcast to nobody here and the connect
    // handshake replays only the state snapshot. Without a resync on the
    // first open the board sits one action short until the next mutation
    // exposes the version gap.
    const { result } = renderHook(() => useGameState('ws-oid', { auditEnabled: true }));

    await act(async () => {
      await result.current.initialize();
    });

    const mountFetches = vi.mocked(api.getAudit).mock.calls.length;
    expect(mountFetches).toBeGreaterThanOrEqual(1);

    const handlers = vi.mocked(ws.createWebSocket).mock.calls.at(-1)![1];
    await act(async () => {
      handlers.onOpen?.();
    });

    expect(vi.mocked(api.getAudit).mock.calls.length).toBeGreaterThan(mountFetches);
    expect(result.current.connected).toBe(true);
  });

  it('does not read the audit log at all while the feed is disabled', async () => {
    // Default posture: nothing on screen is showing the log, so arming it
    // would be a request for nobody.
    const { result } = renderHook(() => useGameState('ws-oid'));

    await act(async () => {
      await result.current.initialize();
    });

    const handlers = vi.mocked(ws.createWebSocket).mock.calls.at(-1)![1];
    await act(async () => {
      handlers.onOpen?.();
    });

    expect(api.getAudit).not.toHaveBeenCalled();
    expect(result.current.audit.records).toEqual([]);
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

    expect(api.addPoint).toHaveBeenCalledWith('oid', 1, false, undefined, undefined);
    expect(result.current.state).toEqual(updatedState);
  });

  it('addPoint applies optimistic to state but defers confirmedState until response', async () => {
    // Mirrors the audit-strip refetch race. Consumers that key off
    // ``confirmedState`` (e.g. the recent-events hook) should not advance
    // their cache key until the server has acknowledged the action —
    // otherwise their refetch races the in-flight POST and misses the
    // freshly-appended audit row.
    const updatedState = {
      ...mockState,
      team_1: { ...mockState.team_1, scores: { set_1: 1 } },
    } as unknown as GameState;
    let resolveAddPoint: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.addPoint).mockReturnValue(
      new Promise((resolve) => {
        resolveAddPoint = resolve;
      }),
    );

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    const stateBefore = result.current.state;
    const confirmedBefore = result.current.confirmedState;
    expect(confirmedBefore).toEqual(mockState);

    let actionPromise: Promise<unknown> = Promise.resolve();
    act(() => {
      actionPromise = result.current.actions.addPoint(1);
    });

    // Optimistic phase: state has advanced, confirmedState has not.
    expect(result.current.state).not.toEqual(stateBefore);
    expect(result.current.confirmedState).toEqual(confirmedBefore);

    await act(async () => {
      resolveAddPoint({ success: true, state: updatedState });
      await actionPromise;
    });

    // Confirmation phase: confirmedState catches up to the server's truth.
    expect(result.current.state).toEqual(updatedState);
    expect(result.current.confirmedState).toEqual(updatedState);
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

    expect(api.addPoint).toHaveBeenCalledWith('oid', 2, true, undefined, undefined);
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

  it('action surfaces the clean ApiError detail, not the raw message', async () => {
    vi.mocked(api.addPoint).mockRejectedValue(
      new api.ApiError(
        409,
        'API POST /game/add-point failed (409): {...}',
        'Set already finished.',
      ),
    );
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      const res = await result.current.actions.addPoint(1);
      expect(res.success).toBe(false);
      expect(res.message).toBe('Set already finished.');
    });

    expect(result.current.error).toBe('Set already finished.');
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

  it('startMatch action calls api.startMatch', async () => {
    vi.mocked(api.startMatch).mockResolvedValue({ success: true, state: mockState });
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      await result.current.actions.startMatch();
    });

    expect(api.startMatch).toHaveBeenCalledWith('oid');
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

  it('refreshCustomization reports failure instead of swallowing it', async () => {
    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    const before = result.current.customization;
    vi.mocked(api.getCustomization).mockRejectedValueOnce(new Error('network down'));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.refreshCustomization();
    });

    // The caller learns the read-back failed (App turns this into a toast),
    // and the last known-good customization is left in place rather than
    // being cleared out from under the panel.
    expect(ok).toBe(false);
    expect(result.current.customization).toEqual(before);

    vi.mocked(api.getCustomization).mockResolvedValue({ 'Team 1 Name': 'Fresh' });
    await act(async () => {
      ok = await result.current.refreshCustomization();
    });
    expect(ok).toBe(true);
  });

  it('refreshCustomization reports failure when there is no oid', async () => {
    const { result } = renderHook(() => useGameState(null));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.refreshCustomization();
    });

    expect(ok).toBe(false);
    expect(api.getCustomization).not.toHaveBeenCalled();
  });

  it('actions reject without an oid instead of requesting a null board', async () => {
    const { result } = renderHook(() => useGameState(null));

    let res: Awaited<ReturnType<typeof result.current.actions.addPoint>> | undefined;
    await act(async () => {
      res = await result.current.actions.addPoint(1);
    });

    expect(res?.success).toBe(false);
    expect(api.addPoint).not.toHaveBeenCalled();
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
