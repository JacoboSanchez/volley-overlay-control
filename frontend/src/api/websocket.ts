/**
 * WebSocket client for real-time state updates.
 */

import type { GameState } from './client';
import { WS_PING_INTERVAL_MS } from '../constants';

export interface StateUpdateMessage {
  type: 'state_update';
  data: GameState;
}

export interface CustomizationUpdateMessage {
  type: 'customization_update';
  data: Record<string, unknown>;
}

export type OverlayMessage = StateUpdateMessage | CustomizationUpdateMessage;

export interface CreateWebSocketHandlers {
  onStateUpdate?: (data: GameState) => void;
  onCustomizationUpdate?: (data: Record<string, unknown>) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
}

export function createWebSocket(
  oid: string,
  {
    onStateUpdate,
    onCustomizationUpdate,
    onOpen,
    onClose,
    onError,
  }: CreateWebSocketHandlers,
): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const url = `${protocol}//${host}/api/v1/ws?oid=${encodeURIComponent(oid)}`;

  const ws = new WebSocket(url);
  let pingInterval: ReturnType<typeof setInterval> | null = null;

  ws.onopen = () => {
    pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
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
      }
    } catch {
      // ignore non-JSON messages
    }
  };

  ws.onclose = (event: CloseEvent) => {
    if (pingInterval) clearInterval(pingInterval);
    onClose?.(event);
  };

  ws.onerror = (event: Event) => {
    onError?.(event);
  };

  return ws;
}
