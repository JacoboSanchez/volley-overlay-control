import { FormEvent, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import './account.css';

export default function ClaimAdminPage() {
  const { ctx, refresh } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [token, setToken] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Once an admin exists the window is closed.
  if (ctx && !ctx.needs_admin_bootstrap) {
    return <Navigate to="/login" replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (password !== confirmPw) {
      setError(t('acc.auth.errorPasswordMismatch'));
      return;
    }
    setBusy(true);
    try {
      await api.claimAdmin(token.trim(), username.trim(), password);
      await refresh();
      navigate('/');
    } catch (err) {
      setError(
        err instanceof api.ApiError && err.status === 403
          ? t('acc.auth.claim.errorToken')
          : t('acc.auth.claim.errorFailed'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>{t('acc.auth.claim.title')}</h1>
          <p className="acc-sub">
            {t('acc.auth.claim.introTokenPrefix')}
            <code>docker logs</code>{', '}<code>journalctl</code>
            {t('acc.auth.claim.introTokenSuffix')}
            {' '}
            {t('acc.auth.claim.introEnvPrefix')}
            <code>ADMIN_BOOTSTRAP_TOKEN</code>
            {t('acc.auth.claim.introEnvMid')}
            <code>data/.admin_bootstrap_token</code>
            {t('acc.auth.claim.introEnvSuffix')}
          </p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>{t('acc.auth.claim.tokenLabel')}</span>
            <input className="acc-input" value={token} autoFocus autoComplete="off"
              onChange={(e) => setToken(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.claim.usernameLabel')}</span>
            <input className="acc-input" value={username} autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.passwordMin8')}</span>
            <input className="acc-input" type="password" value={password}
              autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.confirmPassword')}</span>
            <input className="acc-input" type="password" value={confirmPw}
              autoComplete="new-password" onChange={(e) => setConfirmPw(e.target.value)} />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? t('acc.auth.claim.submitBusy') : t('acc.auth.claim.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
