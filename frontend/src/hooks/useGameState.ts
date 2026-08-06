import {
  useState,
  useCallback,
  useRef,
  useEffect,
  useMemo,
  type Dispatch,
  type SetStateAction,
} from 'react';
import * as api from '../api/board';
import { ApiError } from '../api/http';
import type { GameState, ActionResponse, Team, TeamState } from '../api/board';
import { createWebSocket } from '../api/websocket';
import { useAuditFeed, type AuditFeed } from './useAuditFeed';
import { WS_RECONNECT_BASE_MS, WS_RECONNECT_FACTOR, WS_RECONNECT_MAX_MS } from '../constants';
import { apiErrorMessage } from './useAsyncAction';

type Customization = Record<string, unknown>;

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
  addPoint: (
    team: Team,
    undo?: boolean,
    pointType?: api.PointType,
    errorType?: api.ErrorType,
  ) => Promise<ActionResponse>;
  addSet: (team: Team, undo?: boolean) => Promise<ActionResponse>;
  addTimeout: (team: Team, undo?: boolean) => Promise<ActionResponse>;
  changeServe: (team: Team) => Promise<ActionResponse>;
  setScore: (team: Team, setNumber: number, value: number) => Promise<ActionResponse>;
  setSets: (team: Team, value: number) => Promise<ActionResponse>;
  reset: () => Promise<ActionResponse>;
  setVisibility: (visible: boolean) => Promise<ActionResponse>;
  setSimpleMode: (enabled: boolean) => Promise<ActionResponse>;
  setSetSummary: (enabled: boolean) => Promise<ActionResponse>;
  /** Set the effective display orientation (true = team 2 left). */
  setSwapSides: (swapped: boolean) => Promise<ActionResponse>;
  setSetSummaryStyle: (style: api.SetSummaryStyle) => Promise<ActionResponse>;
  /**
   * Server-side LIFO undo: pops the most recent forward
   * ``add_point``/``add_set``/``add_timeout`` from the audit log
   * and reverses it. Use this for global "Undo last" gestures so
   * the undo stack is shared between clients and survives reload.
   */
  undoLast: () => Promise<ActionResponse>;
  /**
   * Stamps ``match_started_at`` on the server. Idempotent — a second
   * call leaves the original anchor in place. Used by the explicit
   * "Start match" button in the HUD; the first ``addPoint`` arms it
   * automatically too.
   */
  startMatch: () => Promise<ActionResponse>;
}

export interface UseGameStateOptions {
  /**
   * Mirror the board's audit log into ``audit``. Off by default: the log
   * is only needed when something is showing it (the momentum strip or the
   * history drawer), and leaving it off saves the one fetch that arms the
   * live feed. Flipping it on mid-session reads the log then; flipping it
   * off drops the records.
   */
  auditEnabled?: boolean | undefined;
}

export interface UseGameStateResult {
  state: GameState | null;
  /**
   * Mirror of ``state`` that excludes optimistic predictions — only updated
   * from authoritative sources (initial fetch, action response, WS push).
   * Consumers that derive cache keys from state (e.g. the recent-events
   * hook) should depend on this instead of ``state`` to avoid racing the
   * optimistic update against the network round-trip that would actually
   * make the prediction observable on the server.
   */
  confirmedState: GameState | null;
  customization: Customization | null;
  connected: boolean;
  error: string | null;
  /** HTTP status behind ``error`` when it came from an ApiError (null for
   *  network failures and non-HTTP errors) — lets consumers distinguish a
   *  rejected credential (401/403/404) from a transient outage. */
  errorStatus: number | null;
  initialize: () => Promise<void>;
  actions: GameActions;
  /** Re-reads customization from the server. Resolves ``false`` when the
   *  fetch failed (or there is no overlay), so callers that need the
   *  operator to know can surface it. */
  refreshCustomization: () => Promise<boolean>;
  setCustomization: Dispatch<SetStateAction<Customization | null>>;
  /**
   * Live mirror of the board's action log, fed by the same WebSocket.
   * Empty unless ``auditEnabled`` was passed. Consumers project from
   * ``audit.records`` rather than fetching for themselves — see
   * ``useAuditFeed``.
   */
  audit: AuditFeed;
}

/**
 * Central game state hook. Manages session init, WebSocket connection,
 * and exposes all game actions.
 */
export function useGameState(
  oid: string | null,
  { auditEnabled = false }: UseGameStateOptions = {},
): UseGameStateResult {
  const [state, setState] = useState<GameState | null>(null);
  const [confirmedState, setConfirmedState] = useState<GameState | null>(null);
  const [customization, setCustomization] = useState<Customization | null>(null);
  const [connected, setConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);
  // Mirror of `state` used by handleAction so it can synchronously snapshot
  // the current state and apply an optimistic update without relying on an
  // impure setState updater. Updated eagerly on every state write.
  const stateRef = useRef<GameState | null>(null);
  const audit = useAuditFeed(oid, auditEnabled);
  const { onAppend: onAuditAppend, onInvalidate: onAuditInvalidate, onResync } = audit;

  const applyState = useCallback((next: GameState | null, confirmed: boolean = true) => {
    stateRef.current = next;
    setState(next);
    // ``confirmedState`` deliberately excludes optimistic writes so cache
    // keys derived from it (e.g. the recent-events refetch trigger) do
    // not advance until the server has acknowledged the change. Without
    // this gate the optimistic add-point bumps the scoring key
    // immediately, the audit refetch races the in-flight POST, and the
    // newly-appended audit row is missed — producing the "chip appears
    // one action late" symptom.
    if (confirmed) {
      setConfirmedState(next);
    }
  }, []);

  const closeWs = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      // Detach *every* handler, not just the ones whose reconnect
      // behaviour we are suppressing. ``close()`` starts a handshake, it
      // does not drop frames already queued for delivery, so a socket
      // left with ``onmessage`` installed can still fire after this
      // returns — and by then ``oid`` may have moved on. The audit
      // callbacks carry no board identity (they are stable across board
      // changes by design), so such a frame would be applied to the
      // *new* board's feed: with per-board version counters that all
      // start at 0, an old board's version N+1 lines up with a fresh
      // board's N often enough to matter, and the operator sees another
      // board's action in this one's history.
      wsRef.current.onmessage = null;
      wsRef.current.onopen = null;
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
      onAuditAppend,
      onAuditInvalidate,
      onOpen: () => {
        // Successful handshake: reset the backoff so the next outage
        // starts retrying quickly again.
        reconnectAttempts.current = 0;
        setConnected(true);
        // Re-read the audit log on *every* open, including the first.
        // The feed's mount fetch races the handshake: this socket does
        // not exist yet while that fetch is in flight, so an action from
        // another client in that window is broadcast to nobody here, and
        // the connect handshake replays only the state snapshot, never
        // missed audit rows. Without this the board would sit on a log
        // that is one action short until the *next* mutation exposed the
        // version gap. Costs one extra read per board load, against the
        // ~150-200 this hook removed from a five-set match.
        onResync();
      },
      onClose: (event) => {
        setConnected(false);
        // Application-level close codes (4xxx) are terminal: bad request
        // (4400), invalid/revoked credentials (4003) or no session (4004).
        // Reconnecting would just re-fail forever, so stop and surface why.
        if (event.code >= 4000 && event.code <= 4999) {
          if (event.reason) setError(event.reason);
          return;
        }
        // Exponential backoff with jitter: prevents reconnect storms
        // when many clients lose the server simultaneously, and avoids
        // hammering an unreachable server during long outages.
        const attempt = reconnectAttempts.current;
        reconnectAttempts.current = attempt + 1;
        const exp = WS_RECONNECT_BASE_MS * Math.pow(WS_RECONNECT_FACTOR, attempt);
        const capped = Math.min(exp, WS_RECONNECT_MAX_MS);
        const jitter = Math.random() * 0.3 * capped;
        const delay = capped + jitter;
        reconnectTimer.current = setTimeout(connectWs, delay);
      },
      onError: () => setConnected(false),
    });
  }, [oid, closeWs, applyState, onAuditAppend, onAuditInvalidate, onResync]);

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
    // A new overlay starts its reconnect backoff fresh — otherwise a counter
    // left high by the previous overlay's outage would delay the first connect.
    reconnectAttempts.current = 0;
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      setError(null);
      setErrorStatus(null);
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
        // ApiError.message is the verbose "API POST /… failed (403): {json}"
        // debugging string; surface the human-facing ``detail`` instead.
        setError(apiErrorMessage(e, e instanceof Error ? e.message : String(e)));
        setErrorStatus(e instanceof ApiError ? e.status : null);
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

  const handleAction = useCallback(
    async (
      actionFn: (oid: string) => Promise<ActionResponse>,
      optimisticUpdater?: (prev: GameState) => GameState,
    ): Promise<ActionResponse> => {
      // Single narrowing point for the whole action surface: every action
      // needs an overlay id, so checking here lets the callbacks below take
      // a plain ``string`` instead of asserting a nullable one 14 times.
      // Without a board there is nothing to act on — report it like any
      // other rejected action rather than throwing.
      if (!oid) {
        return { success: false, message: 'No overlay session' };
      }
      // Capture the snapshot synchronously from the ref (not from an impure
      // setState updater) so rollback is reliable even if actionFn rejects
      // before React processes the update.
      const snapshot = stateRef.current;
      const shouldApplyOptimistic = Boolean(optimisticUpdater && snapshot);
      if (shouldApplyOptimistic && snapshot && optimisticUpdater) {
        applyState(optimisticUpdater(snapshot), false);
      }
      try {
        const res = await actionFn(oid);
        if (res.success && res.state) {
          applyState(res.state);
        } else if (!res.success && shouldApplyOptimistic) {
          applyState(snapshot, false);
        }
        return res;
      } catch (e) {
        if (shouldApplyOptimistic) {
          applyState(snapshot, false);
        }
        const message = apiErrorMessage(e, e instanceof Error ? e.message : String(e));
        setError(message);
        setErrorStatus(e instanceof ApiError ? e.status : null);
        return { success: false, message };
      }
    },
    [oid, applyState],
  );

  const actions = useMemo<GameActions>(
    () => ({
      addPoint: (team, undo = false, pointType, errorType) =>
        handleAction(
          (id) => api.addPoint(id, team, undo, pointType, errorType),
          undo ? undefined : (prev) => optimisticAddPoint(prev, team),
        ),
      addSet: (team, undo = false) => handleAction((id) => api.addSet(id, team, undo)),
      addTimeout: (team, undo = false) => handleAction((id) => api.addTimeout(id, team, undo)),
      changeServe: (team) => handleAction((id) => api.changeServe(id, team)),
      setScore: (team, setNumber, value) =>
        handleAction((id) => api.setScore(id, team, setNumber, value)),
      setSets: (team, value) => handleAction((id) => api.setSets(id, team, value)),
      reset: () => handleAction((id) => api.resetGame(id)),
      setVisibility: (visible) => handleAction((id) => api.setVisibility(id, visible)),
      setSimpleMode: (enabled) => handleAction((id) => api.setSimpleMode(id, enabled)),
      setSetSummary: (enabled) => handleAction((id) => api.setSetSummary(id, enabled)),
      setSwapSides: (swapped) => handleAction((id) => api.setSwapSides(id, swapped)),
      setSetSummaryStyle: (style) => handleAction((id) => api.setSetSummaryStyle(id, style)),
      undoLast: () => handleAction((id) => api.undoLast(id)),
      startMatch: () => handleAction((id) => api.startMatch(id)),
    }),
    [handleAction],
  );

  const refreshCustomization = useCallback(async (): Promise<boolean> => {
    if (!oid) return false;
    try {
      // Fetch the latest customization from the backend (which already has the
      // just-saved data) and update the local customization state. We deliberately
      // do NOT call initSession here: re-initializing the session loads data from
      // the overlay server, which may still be serving the pre-save snapshot.
      // Doing so would cause the next game action (e.g., addPoint) to broadcast
      // stale team names/colors and visually revert the overlay.
      const cust = await api.getCustomization(oid);
      setCustomization(cust);
      return true;
    } catch {
      // Reported, not swallowed: the caller decides whether this is worth
      // telling the operator about. A refresh that failed right after a
      // save leaves the panel showing values the server does not have,
      // which is exactly the case that needs to be visible; the background
      // locale sync is not.
      return false;
    }
  }, [oid]);

  return {
    state,
    confirmedState,
    customization,
    connected,
    error,
    errorStatus,
    initialize,
    actions,
    refreshCustomization,
    setCustomization,
    audit,
  };
}
