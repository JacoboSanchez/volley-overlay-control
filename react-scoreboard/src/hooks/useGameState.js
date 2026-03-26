import { useState, useCallback, useRef, useEffect } from 'react';
import * as api from '../api/client';
import { createWebSocket } from '../api/websocket';

/**
 * Central game state hook. Manages session init, WebSocket connection,
 * and exposes all game actions.
 */
export function useGameState(oid) {
  const [state, setState] = useState(null);
  const [customization, setCustomization] = useState(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const initRef = useRef(false); // guard against concurrent initialize calls

  /** Safely tear down the current WebSocket without triggering reconnect. */
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
      onOpen: () => setConnected(true),
      onClose: (event) => {
        setConnected(false);
        // Only reconnect for unexpected disconnects
        if (event.code !== 4004) {
          reconnectTimer.current = setTimeout(connectWs, 3000);
        }
      },
      onError: () => setConnected(false),
    });
  }, [oid, closeWs]);

  const initialize = useCallback(async (opts = {}) => {
    if (!oid) {
      setState(null);
      setCustomization(null);
      setConnected(false);
      setError(null);
      return;
    }
    // Prevent overlapping initializations (e.g. StrictMode double-fire)
    if (initRef.current) return;
    initRef.current = true;
    try {
      setError(null);
      const res = await api.initSession(oid, opts);
      if (res.success) {
        setState(res.state);
        const cust = await api.getCustomization(oid);
        setCustomization(cust);
        connectWs();
      } else {
        setError(res.message || 'Session initialization failed');
      }
    } catch (e) {
      setError(e.message);
    } finally {
      initRef.current = false;
    }
  }, [oid, connectWs]);

  // Cleanup on unmount or OID change
  useEffect(() => {
    return () => closeWs();
  }, [oid, closeWs]);

  // Action helpers — all update state from the response
  const handleAction = useCallback(async (actionFn) => {
    try {
      const res = await actionFn();
      if (res.success) {
        setState(res.state);
      }
      return res;
    } catch (e) {
      setError(e.message);
      return { success: false, message: e.message };
    }
  }, []);

  const actions = {
    addPoint: (team, undo = false) => handleAction(() => api.addPoint(oid, team, undo)),
    addSet: (team, undo = false) => handleAction(() => api.addSet(oid, team, undo)),
    addTimeout: (team, undo = false) => handleAction(() => api.addTimeout(oid, team, undo)),
    changeServe: (team) => handleAction(() => api.changeServe(oid, team)),
    setScore: (team, setNumber, value) => handleAction(() => api.setScore(oid, team, setNumber, value)),
    setSets: (team, value) => handleAction(() => api.setSets(oid, team, value)),
    reset: () => handleAction(() => api.resetGame(oid)),
    setVisibility: (visible) => handleAction(() => api.setVisibility(oid, visible)),
    setSimpleMode: (enabled) => handleAction(() => api.setSimpleMode(oid, enabled)),
  };

  const refreshCustomization = useCallback(async () => {
    if (!oid) return;
    try {
      const cust = await api.getCustomization(oid);
      setCustomization(cust);
    } catch (e) {
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
  };
}
