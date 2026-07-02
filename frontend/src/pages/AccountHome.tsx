import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import { useOverlays } from '../hooks/useOverlays';

export default function AccountHome() {
  const { ctx } = useAuth();
  const { t } = useI18n();
  const isAdmin = ctx?.user?.role === 'admin';
  const name = ctx?.user?.display_name || ctx?.user?.username;
  const { overlays, loading, error } = useOverlays();

  return (
    <div>
      <h2>{t('acc.home.welcome', { name: name ?? '' })}</h2>
      <p className="acc-muted">{t('acc.home.intro')}</p>
      {error && <div className="acc-error" style={{ marginTop: 16 }}>{t('acc.reports.errorOverlays')}</div>}
      {!loading && !error && overlays.length === 0 && (
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
        {isAdmin && <Tile to="/admin" title={t('acc.nav.admin')} desc={t('acc.home.tile.admin.desc')} />}
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
