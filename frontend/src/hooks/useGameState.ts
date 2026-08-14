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

interface QueuedMutation {
  run: () => Promise<ActionResponse>;
  resolve: (response: ActionResponse) => void;
  reject: (error: unknown) => void;
}

interface HandleActionOptions {
  /**
   * How many times to replay the mutation against the freshly loaded
   * revision after a ``state_revision_conflict``. Zero (the default) is
   * right for operator gestures — the board changed under them, so
   * repeating is their call. Background writes that carry no operator
   * intent opt in so a remote controller's point cannot silently drop
   * them.
   */
  conflictRetries?: number;
  /** Keep failures out of the shared error banner (background writes). */
  quiet?: boolean;
}

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
  /**
   * Write the operator's UI language onto the overlay customization so
   * OBS-embedded overlays follow it live. Runs through the same
   * serialized mutation queue as every scoring action — a background
   * write racing a point would otherwise send both with the same
   * revision and lose one of them to a 409. Failures stay off the error
   * banner; see ``useOverlayLocaleSync``.
   */
  syncOverlayLocale: (locale: string) => Promise<ActionResponse>;
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
  /** Distinct browser-tab controllers currently attached to this board. */
  controllerCount: number;
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
  const [controllerCount, setControllerCount] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef<number>(0);
  const abortRef = useRef<AbortController | null>(null);
  const activeOidRef = useRef<string | null>(null);
  const mutationQueueRef = useRef<QueuedMutation[]>([]);
  const mutationRunningRef = useRef(false);
  // Mirror of `state` used by handleAction so it can synchronously snapshot
  // the current state and apply an optimistic update without relying on an
  // impure setState updater. Updated eagerly on every state write.
  const stateRef = useRef<GameState | null>(null);
  const audit = useAuditFeed(oid, auditEnabled);
  const { onAppend: onAuditAppend, onInvalidate: onAuditInvalidate, onResync } = audit;

  const applyState = useCallback((next: GameState | null, confirmed: boolean = true) => {
    const currentRevision = stateRef.current?.revision;
    const nextRevision = next?.revision;
    // An HTTP acknowledgement can race a newer remote WS push. Never let the
    // older response roll the board back after another controller advanced it.
    if (
      typeof currentRevision === 'number' &&
      typeof nextRevision === 'number' &&
      nextRevision < currentRevision
    ) {
      return;
    }
    stateRef.current = next;
    setState(next);
    if (next && typeof next.controller_count === 'number') {
      setControllerCount(next.controller_count);
    }
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
      onPresenceUpdate: (count) => setControllerCount(count),
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
        setControllerCount(0);
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
      activeOidRef.current = null;
      applyState(null);
      setCustomization(null);
      setConnected(false);
      setControllerCount(0);
      setError(null);
      return;
    }
    // Revisions are monotonic per board, not globally. Clear the previous
    // board before its revision can make the first snapshot for this OID look
    // stale and therefore be discarded by ``applyState``.
    if (activeOidRef.current !== oid) {
      activeOidRef.current = oid;
      applyState(null);
      setConfirmedState(null);
      setCustomization(null);
      setControllerCount(0);
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
      activeOidRef.current = null;
      closeWs();
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [oid, closeWs]);

  const drainMutationQueue = useCallback(() => {
    if (mutationRunningRef.current) return;
    mutationRunningRef.current = true;

    void (async () => {
      while (mutationQueueRef.current.length > 0) {
        const queued = mutationQueueRef.current.shift();
        if (!queued) continue;
        try {
          queued.resolve(await queued.run());
        } catch (queueError) {
          queued.reject(queueError);
        }
      }
      mutationRunningRef.current = false;
    })();
  }, []);

  const handleAction = useCallback(
    (
      actionFn: (oid: string, expectedRevision?: number) => Promise<ActionResponse>,
      optimisticUpdater?: (prev: GameState) => GameState,
      { conflictRetries = 0, quiet = false }: HandleActionOptions = {},
    ): Promise<ActionResponse> => {
      if (!oid) {
        return Promise.resolve({ success: false, message: 'No overlay session' });
      }
      const actionOid = oid;
      const fail = (message: string, status: number | null): ActionResponse => {
        // Background syncs report through their own caller; surfacing them in
        // the shared banner would blame the operator's next action for a
        // failure they never triggered.
        if (!quiet) {
          setError(message);
          setErrorStatus(status);
        }
        return { success: false, message };
      };
      const attempt = async (retriesLeft: number): Promise<ActionResponse> => {
        // A board switch cancels work still queued for the previous board. An
        // already in-flight response is likewise ignored below.
        if (activeOidRef.current !== actionOid) {
          return { success: false, message: 'Board changed before action was sent.' };
        }
        // Snapshot at execution time, after all earlier actions from this tab
        // acknowledged. Intentional sequences therefore cannot conflict with
        // themselves while remote controllers still get proper protection.
        const snapshot = stateRef.current;
        const shouldApplyOptimistic = Boolean(optimisticUpdater && snapshot);
        if (shouldApplyOptimistic && snapshot && optimisticUpdater) {
          applyState(optimisticUpdater(snapshot), false);
        }
        try {
          const expectedRevision = snapshot?.revision;
          const res = await actionFn(actionOid, expectedRevision);
          if (activeOidRef.current !== actionOid) return res;
          if (res.success && res.state) {
            applyState(res.state);
          } else if (!res.success && shouldApplyOptimistic) {
            applyState(snapshot, false);
          }
          return res;
        } catch (e) {
          if (activeOidRef.current !== actionOid) {
            return { success: false, message: 'Board changed while action was in flight.' };
          }
          if (shouldApplyOptimistic) {
            applyState(snapshot, false);
          }
          if (e instanceof ApiError && e.status === 409 && e.detail === 'state_revision_conflict') {
            try {
              const latest = await api.getState(actionOid);
              if (activeOidRef.current === actionOid) applyState(latest);
              // Operator gestures stop here on purpose: the board moved under
              // them, so the decision to repeat the action is theirs. Callers
              // that opt in (background syncs carrying no operator intent)
              // replay against the revision just loaded instead.
              if (retriesLeft > 0) return attempt(retriesLeft - 1);
              return {
                success: false,
                state: latest,
                message: 'Another controller changed the scoreboard. Latest state loaded.',
              };
            } catch (refreshError) {
              return fail(
                apiErrorMessage(
                  refreshError,
                  refreshError instanceof Error ? refreshError.message : String(refreshError),
                ),
                refreshError instanceof ApiError ? refreshError.status : null,
              );
            }
          }
          return fail(
            apiErrorMessage(e, e instanceof Error ? e.message : String(e)),
            e instanceof ApiError ? e.status : null,
          );
        }
      };

      const run = (): Promise<ActionResponse> => attempt(conflictRetries);

      return new Promise<ActionResponse>((resolve, reject) => {
        mutationQueueRef.current.push({ run, resolve, reject });
        drainMutationQueue();
      });
    },
    [oid, applyState, drainMutationQueue],
  );

  const actions = useMemo<GameActions>(
    () => ({
      addPoint: (team, undo = false, pointType, errorType) =>
        handleAction(
          (id, revision) => api.addPoint(id, team, undo, pointType, errorType, revision),
          undo ? undefined : (prev) => optimisticAddPoint(prev, team),
        ),
      addSet: (team, undo = false) =>
        handleAction((id, revision) => api.addSet(id, team, undo, revision)),
      addTimeout: (team, undo = false) =>
        handleAction((id, revision) => api.addTimeout(id, team, undo, revision)),
      changeServe: (team) => handleAction((id, revision) => api.changeServe(id, team, revision)),
      setScore: (team, setNumber, value) =>
        handleAction((id, revision) => api.setScore(id, team, setNumber, value, revision)),
      setSets: (team, value) =>
        handleAction((id, revision) => api.setSets(id, team, value, revision)),
      reset: () => handleAction((id, revision) => api.resetGame(id, revision)),
      setVisibility: (visible) =>
        handleAction((id, revision) => api.setVisibility(id, visible, revision)),
      setSimpleMode: (enabled) =>
        handleAction((id, revision) => api.setSimpleMode(id, enabled, revision)),
      setSetSummary: (enabled) =>
        handleAction((id, revision) => api.setSetSummary(id, enabled, revision)),
      setSwapSides: (swapped) =>
        handleAction((id, revision) => api.setSwapSides(id, swapped, revision)),
      setSetSummaryStyle: (style) =>
        handleAction((id, revision) => api.setSetSummaryStyle(id, style, revision)),
      undoLast: () => handleAction((id, revision) => api.undoLast(id, revision)),
      startMatch: () => handleAction((id, revision) => api.startMatch(id, revision)),
      syncOverlayLocale: (locale) =>
        handleAction(
          (id, revision) => api.updateCustomization(id, { locale }, revision),
          undefined,
          { conflictRetries: 1, quiet: true },
        ),
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
    controllerCount,
    error,
    errorStatus,
    initialize,
    actions,
    refreshCustomization,
    setCustomization,
    audit,
  };
}
