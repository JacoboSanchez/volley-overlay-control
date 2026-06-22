import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';

export default function AccountHome() {
  const { ctx } = useAuth();
  const { t } = useI18n();
  const name = ctx?.user?.display_name || ctx?.user?.username;
  const [overlayCount, setOverlayCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ovs = await api.getOverlays();
        if (!cancelled) setOverlayCount(ovs.length);
      } catch {
        /* leave unknown — don't push an error onto the dashboard */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div>
      <h2>{t('acc.home.welcome', { name: name ?? '' })}</h2>
      <p className="acc-muted">{t('acc.home.intro')}</p>
      {overlayCount === 0 && (
        <div className="acc-info" style={{ marginTop: 16 }}>
          <strong>{t('acc.home.getStarted')}</strong> {t('acc.home.getStartedBody')}{' '}
          <Link to="/overlays">{t('acc.cta.createScoreboard')}</Link>
        </div>
      )}
      <div className="acc-tile-grid">
        <Tile to="/overlays" title={t('acc.nav.overlays')} desc={t('acc.home.tile.overlays.desc')} />
        <Tile to="/teams" title={t('acc.nav.teams')} desc={t('acc.home.tile.teams.desc')} />
        <Tile to="/presets" title={t('acc.nav.presets')} desc={t('acc.home.tile.presets.desc')} />
        <Tile to="/reports" title={t('acc.nav.reports')} desc={t('acc.home.tile.reports.desc')} />
        <Tile to="/account" title={t('acc.nav.account')} desc={t('acc.home.tile.account.desc')} />
      </div>
    </div>
  );
}

function Tile({ to, title, desc }: { to: string; title: string; desc: string }) {
  return (
    <Link to={to} className="acc-tile">
      <div className="acc-tile-title">{title}</div>
      <div className="acc-muted">{desc}</div>
    </Link>
  );
}
