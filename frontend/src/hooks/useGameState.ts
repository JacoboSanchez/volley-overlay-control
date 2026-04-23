import { useState, useCallback, useRef, useEffect, useMemo, Dispatch, SetStateAction } from 'react';
import * as api from '../api/client';
import type { GameState, ActionResponse, Team } from '../api/client';
import type { components } from '../api/schema';
import { createWebSocket } from '../api/websocket';

type Customization = Record<string, unknown>;
type TeamState = components['schemas']['TeamState'];

// Optimistic prediction of the next state after a successful addPoint. The
// scoring team gains one point and takes the serve; the server later sends the
// authoritative state via HTTP response and WebSocket broadcast. Undo actions
// are not predicted — their effect on match/set boundaries is non-trivial.
function optimisticAddPoint(prev: GameState, team: Team): GameState {
  // Prefer the server's current_set; fall back to the same derivation the App
  // uses (completed sets + 1), so a missing/zero value doesn't push the point
  // into set_0 and cause a flicker when the authoritative state arrives.
  const derivedSet = (prev.team_1?.sets ?? 0) + (prev.team_2?.sets ?? 0) + 1;
  const setNum = prev.current_set || derivedSet;
  const setKey = `set_${setNum}`;
  const updateTeam = (t: TeamState, isScorer: boolean): TeamState => {
    const scores = (t.scores ?? {}) as Record<string, unknown>;
    const current = typeof scores[setKey] === 'number' ? (scores[setKey] as number) : 0;
    return {
      ...t,
      serving: isScorer,
      scores: isScorer ? { ...scores, [setKey]: current + 1 } : scores,
    };
  };
  return {
    ...prev,
    serve: team === 1 ? 'A' : 'B',
    team_1: updateTeam(prev.team_1, team === 1),
    team_2: updateTeam(prev.team_2, team === 2),
  };
}

export interface GameActions {
  addPoint: (team: Team, undo?: boolean) => Promise<ActionResponse>;
  addSet: (team: Team, undo?: boolean) => Promise<ActionResponse>;
  addTimeout: (team: Team, undo?: boolean) => Promise<ActionResponse>;
  changeServe: (team: Team) => Promise<ActionResponse>;
  setScore: (team: Team, setNumber: number, value: number) => Promise<ActionResponse>;
  setSets: (team: Team, value: number) => Promise<ActionResponse>;
  reset: () => Promise<ActionResponse>;
  setVisibility: (visible: boolean) => Promise<ActionResponse>;
  setSimpleMode: (enabled: boolean) => Promise<ActionResponse>;
}

export interface UseGameStateResult {
  state: GameState | null;
  customization: Customization | null;
  connected: boolean;
  error: string | null;
  initialize: () => Promise<void>;
  actions: GameActions;
  refreshCustomization: () => Promise<void>;
  setCustomization: Dispatch<SetStateAction<Customization | null>>;
}

/**
 * Central game state hook. Manages session init, WebSocket connection,
 * and exposes all game actions.
 */
export function useGameState(oid: string | null): UseGameStateResult {
  const [state, setState] = useState<GameState | null>(null);
  const [customization, setCustomization] = useState<Customization | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Mirror of `state` used by handleAction so it can synchronously snapshot
  // the current state and apply an optimistic update without relying on an
  // impure setState updater. Updated eagerly on every state write.
  const stateRef = useRef<GameState | null>(null);

  const applyState = useCallback((next: GameState | null) => {
    stateRef.current = next;
    setState(next);
  }, []);

  const closeWs = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connectWs = useCallback(() => {
    if (!oid) return;
    closeWs();
    wsRef.current = createWebSocket(oid, {
      onStateUpdate: (newState) => applyState(newState),
      onCustomizationUpdate: (newCust) => setCustomization(newCust),
      onOpen: () => setConnected(true),
      onClose: (event) => {
        setConnected(false);
        if (event.code !== 4004) {
          reconnectTimer.current = setTimeout(connectWs, 3000);
        }
      },
      onError: () => setConnected(false),
    });
  }, [oid, closeWs, applyState]);

  const initialize = useCallback(async () => {
    if (!oid) {
      applyState(null);
      setCustomization(null);
      setConnected(false);
      setError(null);
      return;
    }
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      setError(null);
      const res = await api.initSession(oid);
      if (controller.signal.aborted) return;
      if (res.success && res.state) {
        applyState(res.state);
        const cust = await api.getCustomization(oid);
        if (controller.signal.aborted) return;
        setCustomization(cust);
        connectWs();
      } else {
        setError(res.message || 'Session initialization failed');
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    }
  }, [oid, connectWs, applyState]);

  useEffect(() => {
    return () => {
      closeWs();
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [oid, closeWs]);

  const handleAction = useCallback(async (
    actionFn: () => Promise<ActionResponse>,
    optimisticUpdater?: (prev: GameState) => GameState,
  ): Promise<ActionResponse> => {
    // Capture the snapshot synchronously from the ref (not from an impure
    // setState updater) so rollback is reliable even if actionFn rejects
    // before React processes the update.
    const snapshot = stateRef.current;
    const shouldApplyOptimistic = Boolean(optimisticUpdater && snapshot);
    if (shouldApplyOptimistic && snapshot && optimisticUpdater) {
      applyState(optimisticUpdater(snapshot));
    }
    try {
      const res = await actionFn();
      if (res.success && res.state) {
        applyState(res.state);
      } else if (!res.success && shouldApplyOptimistic) {
        applyState(snapshot);
      }
      return res;
    } catch (e) {
      if (shouldApplyOptimistic) {
        applyState(snapshot);
      }
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      return { success: false, message };
    }
  }, [applyState]);

  const actions = useMemo<GameActions>(() => ({
    addPoint: (team, undo = false) => handleAction(
      () => api.addPoint(oid!, team, undo),
      undo ? undefined : (prev) => optimisticAddPoint(prev, team),
    ),
    addSet: (team, undo = false) => handleAction(() => api.addSet(oid!, team, undo)),
    addTimeout: (team, undo = false) => handleAction(() => api.addTimeout(oid!, team, undo)),
    changeServe: (team) => handleAction(() => api.changeServe(oid!, team)),
    setScore: (team, setNumber, value) => handleAction(() => api.setScore(oid!, team, setNumber, value)),
    setSets: (team, value) => handleAction(() => api.setSets(oid!, team, value)),
    reset: () => handleAction(() => api.resetGame(oid!)),
    setVisibility: (visible) => handleAction(() => api.setVisibility(oid!, visible)),
    setSimpleMode: (enabled) => handleAction(() => api.setSimpleMode(oid!, enabled)),
  }), [oid, handleAction]);

  const refreshCustomization = useCallback(async () => {
    if (!oid) return;
    try {
      // Fetch the latest customization from the backend (which already has the
      // just-saved data) and update the local customization state. We deliberately
      // do NOT call initSession here: re-initializing the session loads data from
      // the overlay server, which may still be serving the pre-save snapshot.
      // Doing so would cause the next game action (e.g., addPoint) to broadcast
      // stale team names/colors and visually revert the overlay.
      const cust = await api.getCustomization(oid);
      setCustomization(cust);
    } catch {
      // ignore
    }
  }, [oid]);

  return {
    state,
    customization,
    connected,
    error,
    initialize,
    actions,
    refreshCustomization,
    setCustomization,
  };
}
