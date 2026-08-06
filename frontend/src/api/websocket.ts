/**
 * WebSocket client for real-time state updates.
 */

import type { AuditRecord, GameState } from './client';
import { getControlToken, getPublicUser } from './client';
import { WS_PING_INTERVAL_MS } from '../constants';

export interface StateUpdateMessage {
  type: 'state_update';
  data: GameState;
}

export interface CustomizationUpdateMessage {
  type: 'customization_update';
  data: Record<string, unknown>;
}

/** One audit row was appended. ``version`` is the log's mutation counter
 *  after the write, so a listener holding ``version - 1`` knows its copy
 *  extends contiguously and anything else means it missed a message. */
export interface AuditAppendMessage {
  type: 'audit_append';
  data: { version: number; record: AuditRecord };
}

/** The log changed in a way that is not a simple append — an undo
 *  tombstone hid an earlier row, a rapid-pair recovery restored one, the
 *  log was cleared, or rotation dropped history. Re-read ``GET /audit``. */
export interface AuditInvalidateMessage {
  type: 'audit_invalidate';
  data: { version: number; record: null };
}

export type OverlayMessage =
  StateUpdateMessage | CustomizationUpdateMessage | AuditAppendMessage | AuditInvalidateMessage;

export interface CreateWebSocketHandlers {
  onStateUpdate?: (data: GameState) => void;
  onCustomizationUpdate?: (data: Record<string, unknown>) => void;
  /** A new audit row arrived. See ``AuditAppendMessage``. */
  onAuditAppend?: (version: number, record: AuditRecord) => void;
  /** The audit log must be re-read. See ``AuditInvalidateMessage``. */
  onAuditInvalidate?: (version: number) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
}

export function createWebSocket(
  oid: string,
  {
    onStateUpdate,
    onCustomizationUpdate,
    onAuditAppend,
    onAuditInvalidate,
    onOpen,
    onClose,
    onError,
  }: CreateWebSocketHandlers,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  // Stream by control token (operator), username+oid (public bookmark), or
  // oid + session cookie (owner).
  const token = getControlToken();
  const user = getPublicUser();
  let query: string;
  if (token) query = `c=${encodeURIComponent(token)}`;
  else if (user) query = `u=${encodeURIComponent(user)}&oid=${encodeURIComponent(oid)}`;
  else query = `oid=${encodeURIComponent(oid)}`;
  const url = `${protocol}//${host}/api/v1/ws?${query}`;

  const ws = new WebSocket(url);
  let pingInterval: ReturnType<typeof setInterval> | null = null;

  const stopPing = () => {
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
  };

  ws.onopen = () => {
    pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
        return;
      }
      // Self-clearing rather than relying solely on ``onclose``: a caller
      // tearing this socket down detaches the handlers before calling
      // ``close()`` (see ``closeWs``), so the close path never runs and
      // the interval would outlive the socket — one leaked timer per
      // board switch and per reconnect, for the life of the tab.
      stopPing();
    }, WS_PING_INTERVAL_MS);
    onOpen?.();
  };

  ws.onmessage = (event: MessageEvent) => {
    if (event.data === 'pong') return;
    try {
      const msg = JSON.parse(event.data) as OverlayMessage;
      if (msg.type === 'state_update') {
        onStateUpdate?.(msg.data);
      } else if (msg.type === 'customization_update') {
        onCustomizationUpdate?.(msg.data);
      } else if (msg.type === 'audit_append') {
        onAuditAppend?.(msg.data.version, msg.data.record);
      } else if (msg.type === 'audit_invalidate') {
        onAuditInvalidate?.(msg.data.version);
      }
    } catch {
      // ignore non-JSON messages
    }
  };

  ws.onclose = (event: CloseEvent) => {
    stopPing();
    onClose?.(event);
  };

  ws.onerror = (event: Event) => {
    onError?.(event);
  };

  return ws;
}
