import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import './account.css';

export default function LoginPage() {
  const { ctx, refresh } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const res = await api.login(username.trim(), password);
      await refresh();
      navigate(res.must_change_password ? '/change-password' : '/');
    } catch (err) {
      // Only a 401 means bad credentials. Anything else (403 deactivated
      // account, 429 rate-limit lockout, 5xx/network) has its own cause —
      // masking it as "invalid password" misleads a locked-out user.
      if (err instanceof api.ApiError && err.status !== 401) {
        setError(err.detail || t('acc.auth.login.errorFailed'));
      } else if (err instanceof api.ApiError) {
        setError(t('acc.auth.login.errorInvalid'));
      } else {
        setError(t('acc.auth.login.errorNetwork'));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>{t('acc.auth.login.title')}</h1>
          <p className="acc-sub">{t('acc.auth.brand')}</p>
          {error && <div className="acc-error">{error}</div>}
          {ctx?.needs_admin_bootstrap && (
            <div className="acc-info">
              {t('acc.auth.login.bootstrapPrefix')}
              <Link to="/claim-admin">{t('acc.auth.login.bootstrapLink')}</Link>
              {t('acc.auth.login.bootstrapSuffix')}
            </div>
          )}
          <label className="acc-field">
            <span>{t('acc.admin.username')}</span>
            <input
              className="acc-input"
              value={username}
              autoFocus
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.password')}</span>
            <input
              className="acc-input"
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? t('acc.auth.login.submitBusy') : t('acc.auth.login.submit')}
            </button>
          </div>
          {/* While the first admin is unclaimed, registering an ordinary
              account is a first-run trap — steer to /claim-admin only. */}
          {ctx && !ctx.needs_admin_bootstrap && (ctx.registration_open ? (
            <p className="acc-sub" style={{ marginTop: 18, marginBottom: 0 }}>
              {t('acc.auth.login.noAccountPrefix')}
              <Link to="/register">{t('acc.auth.login.noAccountLink')}</Link>
            </p>
          ) : (
            <p className="acc-sub" style={{ marginTop: 18, marginBottom: 0 }}>
              {t('acc.auth.login.signupClosed')}
            </p>
          ))}
        </form>
      </div>
    </div>
  );
}
