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

  const applyState = useCallback((newState) => {
    setState(newState);
  }, []);

  const connectWs = useCallback(() => {
    if (!oid) return;
    if (wsRef.current) {
      wsRef.current.close();
    }
    wsRef.current = createWebSocket(oid, {
      onStateUpdate: applyState,
      onOpen: () => setConnected(true),
      onClose: (event) => {
        setConnected(false);
        if (event.code !== 4004) {
          reconnectTimer.current = setTimeout(connectWs, 3000);
        }
      },
      onError: () => setConnected(false),
    });
  }, [oid, applyState]);

  const initialize = useCallback(async (opts = {}) => {
    if (!oid) return;
    try {
      setError(null);
      const res = await api.initSession(oid, opts);
      if (res.success) {
        applyState(res.state);
        const cust = await api.getCustomization(oid);
        setCustomization(cust);
        connectWs();
      } else {
        setError(res.message || 'Session initialization failed');
      }
    } catch (e) {
      setError(e.message);
    }
  }, [oid, applyState, connectWs]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, []);

  // Action helpers — all update state from the response
  const handleAction = useCallback(async (actionFn) => {
    try {
      const res = await actionFn();
      if (res.success) {
        applyState(res.state);
      }
      return res;
    } catch (e) {
      setError(e.message);
      return { success: false, message: e.message };
    }
  }, [applyState]);

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

  return {
    state,
    customization,
    connected,
    error,
    initialize,
    actions,
  };
}
