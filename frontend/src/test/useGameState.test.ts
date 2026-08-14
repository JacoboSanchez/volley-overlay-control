import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGameState } from '../hooks/useGameState';
import * as api from '../api/board';
import { ApiError } from '../api/http';
import * as ws from '../api/websocket';

vi.mock('../api/http', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
}));

vi.mock('../api/board', () => ({
  initSession: vi.fn(),
  getState: vi.fn(),
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
  setSwapSides: vi.fn(),
  setSetSummary: vi.fn(),
  setSetSummaryStyle: vi.fn(),
  updateCustomization: vi.fn(),
}));

vi.mock('../api/websocket', () => ({
  createWebSocket: vi.fn(),
}));

import type { GameState } from '../api/board';

const mockState = {
  revision: 3,
  controller_count: 1,
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
    vi.mocked(api.getState).mockResolvedValue(mockState);
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
      new ApiError(
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

  it('tracks aggregate controller presence from the WebSocket', async () => {
    const { result } = renderHook(() => useGameState('ws-oid'));
    await act(async () => {
      await result.current.initialize();
    });

    expect(result.current.controllerCount).toBe(1);
    const handlers = vi.mocked(ws.createWebSocket).mock.calls.at(-1)![1];
    act(() => {
      handlers.onPresenceUpdate?.(2, [
        { client_id: 'tab-main-a', label: null },
        { client_id: 'tab-main-b', label: 'Auxiliar' },
      ]);
    });
    expect(result.current.controllerCount).toBe(2);
  });

  it('preserves a newer presence update across an equal-revision HTTP response', async () => {
    const wsState = { ...mockState, revision: 4, controller_count: 1 } as unknown as GameState;
    const httpState = { ...wsState, controller_count: 1 } as unknown as GameState;
    let resolveAction: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.addPoint).mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );

    const { result } = renderHook(() => useGameState('ws-oid'));
    await act(async () => {
      await result.current.initialize();
    });
    const handlers = vi.mocked(ws.createWebSocket).mock.calls.at(-1)![1];

    let actionPromise: Promise<unknown> = Promise.resolve();
    act(() => {
      actionPromise = result.current.actions.addPoint(1);
      handlers.onStateUpdate?.(wsState);
      handlers.onPresenceUpdate?.(2, [
        { client_id: 'tab-main-a', label: null },
        { client_id: 'tab-main-b', label: null },
      ]);
    });
    expect(result.current.controllerCount).toBe(2);

    await act(async () => {
      resolveAction({ success: true, state: httpState });
      await actionPromise;
    });

    expect(result.current.state?.revision).toBe(4);
    expect(result.current.controllerCount).toBe(2);
  });

  it('accepts a lower revision when switching to a different board', async () => {
    const high = { ...mockState, revision: 20 } as unknown as GameState;
    const low = { ...mockState, revision: 1 } as unknown as GameState;
    vi.mocked(api.initSession).mockResolvedValueOnce({ success: true, state: high });

    const { result, rerender } = renderHook(({ oid }) => useGameState(oid), {
      initialProps: { oid: 'board-a' },
    });
    await act(async () => {
      await result.current.initialize();
    });
    expect(result.current.state?.revision).toBe(20);

    vi.mocked(api.initSession).mockResolvedValueOnce({ success: true, state: low });
    rerender({ oid: 'board-b' });
    await act(async () => {
      await result.current.initialize();
    });
    expect(result.current.state?.revision).toBe(1);
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

    expect(api.addPoint).toHaveBeenCalledWith('oid', 1, false, undefined, undefined, 3);
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

    expect(api.addPoint).toHaveBeenCalledWith('oid', 2, true, undefined, undefined, 3);
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
      new ApiError(409, 'API POST /game/add-point failed (409): {...}', 'Set already finished.'),
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

  it('reloads authoritative state after a revision conflict', async () => {
    const latest = {
      ...mockState,
      revision: 4,
      team_2: { ...mockState.team_2, scores: { set_1: 1 } },
    } as unknown as GameState;
    vi.mocked(api.addPoint).mockRejectedValue(
      new ApiError(409, 'conflict', 'state_revision_conflict'),
    );
    vi.mocked(api.getState).mockResolvedValue(latest);

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      const response = await result.current.actions.addPoint(1);
      expect(response).toMatchObject({ success: false, state: latest });
    });

    expect(api.getState).toHaveBeenCalledWith('oid');
    expect(result.current.state).toEqual(latest);
    expect(result.current.error).toBeNull();
  });

  it('sends the overlay locale sync behind in-flight mutations, not beside them', async () => {
    const afterPoint = { ...mockState, revision: 4 } as unknown as GameState;
    let resolvePoint: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.addPoint).mockReturnValue(
      new Promise((resolve) => {
        resolvePoint = resolve;
      }),
    );
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    let pointPromise: Promise<unknown> = Promise.resolve();
    let localePromise: Promise<unknown> = Promise.resolve();
    act(() => {
      pointPromise = result.current.actions.addPoint(1);
      localePromise = result.current.actions.syncOverlayLocale('es');
    });
    // Still queued: sending it now would reuse the point's revision and
    // one of the two would come back 409.
    expect(api.updateCustomization).not.toHaveBeenCalled();

    await act(async () => {
      resolvePoint({ success: true, state: afterPoint });
      await pointPromise;
      await localePromise;
    });

    expect(api.updateCustomization).toHaveBeenCalledWith('oid', { locale: 'es' }, 4);
  });

  it('replays the locale sync against the fresh revision after a remote conflict', async () => {
    const latest = { ...mockState, revision: 9 } as unknown as GameState;
    vi.mocked(api.updateCustomization)
      .mockRejectedValueOnce(new ApiError(409, 'conflict', 'state_revision_conflict'))
      .mockResolvedValueOnce({ success: true });
    vi.mocked(api.getState).mockResolvedValue(latest);

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      const res = await result.current.actions.syncOverlayLocale('es');
      expect(res.success).toBe(true);
    });

    expect(api.updateCustomization).toHaveBeenNthCalledWith(1, 'oid', { locale: 'es' }, 3);
    expect(api.updateCustomization).toHaveBeenNthCalledWith(2, 'oid', { locale: 'es' }, 9);
    expect(result.current.error).toBeNull();
  });

  it('keeps a failed background locale sync out of the operator error banner', async () => {
    vi.mocked(api.updateCustomization).mockRejectedValue(new Error('overlay unreachable'));

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    await act(async () => {
      const res = await result.current.actions.syncOverlayLocale('es');
      expect(res.success).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.errorStatus).toBeNull();
  });

  it('queues a customization save behind an in-flight display action', async () => {
    const afterToggle = { ...mockState, revision: 6, simple_mode: true } as unknown as GameState;
    let resolveToggle: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.setSimpleMode).mockReturnValue(
      new Promise((resolve) => {
        resolveToggle = resolve;
      }),
    );
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    let togglePromise: Promise<unknown> = Promise.resolve();
    let savePromise: Promise<unknown> = Promise.resolve();
    act(() => {
      togglePromise = result.current.actions.setSimpleMode(true);
      savePromise = result.current.actions.saveCustomization({ 'Team 1 Name': 'Home' });
    });
    expect(api.updateCustomization).not.toHaveBeenCalled();

    await act(async () => {
      resolveToggle({ success: true, state: afterToggle });
      await togglePromise;
      await savePromise;
    });

    // Snapshotted after the toggle landed, so the two never share a revision.
    expect(api.updateCustomization).toHaveBeenCalledWith('oid', { 'Team 1 Name': 'Home' }, 6);
  });

  it('does not let an older HTTP acknowledgement overwrite a newer WS state', async () => {
    const httpState = { ...mockState, revision: 4 } as unknown as GameState;
    const wsState = {
      ...mockState,
      revision: 5,
      team_2: { ...mockState.team_2, scores: { set_1: 2 } },
    } as unknown as GameState;
    let resolveAction: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.addPoint).mockReturnValue(
      new Promise((resolve) => {
        resolveAction = resolve;
      }),
    );

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });
    const handlers = vi.mocked(ws.createWebSocket).mock.calls.at(-1)![1];

    let actionPromise: Promise<unknown> = Promise.resolve();
    act(() => {
      actionPromise = result.current.actions.addPoint(1);
      handlers.onStateUpdate?.(wsState);
    });
    await act(async () => {
      resolveAction({ success: true, state: httpState });
      await actionPromise;
    });

    expect(result.current.state).toEqual(wsState);
    expect(result.current.confirmedState).toEqual(wsState);
  });

  it('serializes same-tab mutations so intentional sequences do not self-conflict', async () => {
    const afterPoint = { ...mockState, revision: 4 } as unknown as GameState;
    const afterSimple = { ...afterPoint, revision: 5, simple_mode: true } as unknown as GameState;
    let resolvePoint: (value: { success: true; state: GameState }) => void = () => {};
    vi.mocked(api.addPoint).mockReturnValue(
      new Promise((resolve) => {
        resolvePoint = resolve;
      }),
    );
    vi.mocked(api.setSimpleMode).mockResolvedValue({ success: true, state: afterSimple });

    const { result } = renderHook(() => useGameState('oid'));
    await act(async () => {
      await result.current.initialize();
    });

    let pointPromise: Promise<unknown> = Promise.resolve();
    let simplePromise: Promise<unknown> = Promise.resolve();
    act(() => {
      pointPromise = result.current.actions.addPoint(1);
      simplePromise = result.current.actions.setSimpleMode(true);
    });
    expect(api.setSimpleMode).not.toHaveBeenCalled();

    await act(async () => {
      resolvePoint({ success: true, state: afterPoint });
      await pointPromise;
      await simplePromise;
    });

    expect(api.setSimpleMode).toHaveBeenCalledWith('oid', true, 4);
    expect(result.current.state).toEqual(afterSimple);
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

    expect(api.resetGame).toHaveBeenCalledWith('oid', 3);
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

    expect(api.undoLast).toHaveBeenCalledWith('oid', 3);
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

    expect(api.startMatch).toHaveBeenCalledWith('oid', 3);
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

    expect(api.setVisibility).toHaveBeenCalledWith('oid', false, 3);
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

  it('detaches every handler when closing, so a queued frame cannot cross boards', async () => {
    // ``close()`` starts a handshake; it does not drop frames already
    // queued for delivery. The audit callbacks carry no board identity,
    // so a late frame from the previous board's socket would otherwise be
    // applied to the new board's feed — and per-board version counters
    // all start at 0, so an old N+1 lines up with a fresh N.
    const socket = {
      close: vi.fn(),
      onclose: null,
      onerror: null,
      onmessage: (() => {}) as unknown,
      onopen: (() => {}) as unknown,
    };
    vi.mocked(ws.createWebSocket).mockReturnValue(socket as unknown as WebSocket);

    const { result, unmount } = renderHook(() => useGameState('ws-oid'));
    await act(async () => {
      await result.current.initialize();
    });

    unmount();

    expect(socket.close).toHaveBeenCalled();
    expect(socket.onmessage).toBeNull();
    expect(socket.onopen).toBeNull();
    expect(socket.onclose).toBeNull();
    expect(socket.onerror).toBeNull();
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
