import { useState, useCallback, useRef, useEffect, useMemo, Dispatch, SetStateAction } from 'react';
import * as api from '../api/client';
import type { GameState, ActionResponse, Team } from '../api/client';
import { createWebSocket } from '../api/websocket';

type Customization = Record<string, unknown>;

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
      onStateUpdate: (newState) => setState(newState),
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
  }, [oid, closeWs]);

  const initialize = useCallback(async () => {
    if (!oid) {
      setState(null);
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
        setState(res.state);
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
  }, [oid, connectWs]);

  useEffect(() => {
    return () => {
      closeWs();
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [oid, closeWs]);

  const handleAction = useCallback(async (actionFn: () => Promise<ActionResponse>): Promise<ActionResponse> => {
    try {
      const res = await actionFn();
      if (res.success && res.state) {
        setState(res.state);
      }
      return res;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      return { success: false, message };
    }
  }, []);

  const actions = useMemo<GameActions>(() => ({
    addPoint: (team, undo = false) => handleAction(() => api.addPoint(oid!, team, undo)),
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
