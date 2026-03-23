/**
 * WebSocket client for real-time state updates.
 */

export function createWebSocket(oid, { onStateUpdate, onOpen, onClose, onError }) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const url = `${protocol}//${host}/api/v1/ws?oid=${encodeURIComponent(oid)}`;

  const ws = new WebSocket(url);
  let pingInterval = null;

  ws.onopen = () => {
    pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping');
      }
    }, 25000);
    onOpen?.();
  };

  ws.onmessage = (event) => {
    if (event.data === 'pong') return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'state_update') {
        onStateUpdate?.(msg.data);
      }
    } catch {
      // ignore non-JSON messages
    }
  };

  ws.onclose = (event) => {
    if (pingInterval) clearInterval(pingInterval);
    onClose?.(event);
  };

  ws.onerror = (event) => {
    onError?.(event);
  };

  return ws;
}
