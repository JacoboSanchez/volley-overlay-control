import { useEffect, useState } from 'react';
import { useI18n } from '../i18n';

export interface ConnectionStatusProps {
  /** Whether the realtime WebSocket is currently connected. */
  connected: boolean;
  /** Distinct control tabs on this board, including this one. */
  controllerCount?: number;
  /**
   * Grace period before an offline state is announced. Quick socket
   * blips during page transitions or set-end archive flushes resolve
   * within a second; flashing a "Reconnecting…" pill for those is
   * noisier than helpful.
   */
  graceMs?: number;
}

/**
 * Persistent pill announcing realtime sync status. Rendered above the
 * scoreboard so the operator can see at a glance when actions risk
 * being delayed by a flaky link.
 *
 * Stays invisible while the socket is healthy — flashing a permanent
 * "Online" badge would compete with the score for the operator's
 * attention without adding information. Surfaces an amber pill once
 * the disconnect outlives the grace window, with ``aria-live`` so
 * screen readers also pick up the transition.
 */
export default function ConnectionStatus({
  connected,
  controllerCount = 0,
  graceMs = 1500,
}: ConnectionStatusProps) {
  const { t } = useI18n();
  const [showOffline, setShowOffline] = useState(false);

  useEffect(() => {
    if (connected) {
      setShowOffline(false);
      return undefined;
    }
    const timer = setTimeout(() => setShowOffline(true), graceMs);
    return () => clearTimeout(timer);
  }, [connected, graceMs]);

  if (connected && controllerCount > 1) {
    const label = t('conn.controllers', { count: controllerCount });
    return (
      <div
        className="connection-status connection-status-presence"
        role="status"
        aria-live="polite"
        aria-label={label}
        data-testid="controller-presence"
      >
        <span className="material-icons" aria-hidden="true">
          group
        </span>
        <span className="connection-status-label">{label}</span>
      </div>
    );
  }

  if (connected || !showOffline) {
    return (
      <div
        className="connection-status connection-status-hidden"
        role="status"
        aria-live="polite"
        aria-label={t('conn.online')}
      />
    );
  }

  return (
    <div
      className="connection-status connection-status-offline"
      role="status"
      aria-live="polite"
      aria-label={t('conn.reconnecting')}
      data-testid="connection-status"
    >
      <span className="material-icons" aria-hidden="true">
        cloud_off
      </span>
      <span className="connection-status-label">{t('conn.reconnecting')}</span>
    </div>
  );
}
