import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import './account.css';

export default function RegisterPage() {
  const { ctx, refresh } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Don't redirect silently when self-signup is off (or the app still needs its
  // first admin) — explain why and point the visitor at the right place. The
  // bootstrap branch applies even while registration is open: an ordinary
  // account created before the first admin exists is a first-run trap.
  if (ctx && (!ctx.registration_open || ctx.needs_admin_bootstrap)) {
    return (
      <div className="acc-shell">
        <div className="acc-auth">
          <div className="acc-card">
            <h1>{t('acc.auth.register.disabledTitle')}</h1>
            <p className="acc-sub">
              {ctx.needs_admin_bootstrap
                ? t('acc.auth.register.disabledNoAdmin')
                : t('acc.auth.register.disabledClosed')}
            </p>
            <div className="acc-info">
              {ctx.needs_admin_bootstrap ? (
                <>
                  {t('acc.auth.register.disabledBootstrapPrefix')}
                  <Link to="/claim-admin">{t('acc.auth.register.disabledBootstrapLink')}</Link>
                  {t('acc.auth.register.disabledBootstrapSuffix')}
                </>
              ) : (
                <>
                  {t('acc.auth.register.disabledAskPrefix')}
                  <Link to="/login">{t('acc.auth.register.disabledAskLink')}</Link>
                  {t('acc.auth.register.disabledAskSuffix')}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
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
      await api.registerAccount(username.trim(), password, undefined, email.trim() || undefined);
      await refresh();
      navigate('/');
    } catch (err) {
      setError(err instanceof api.ApiError && err.status === 400
        ? t('acc.auth.register.errorTaken')
        : t('acc.auth.register.errorFailed'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>{t('acc.auth.register.title')}</h1>
          <p className="acc-sub">{t('acc.auth.brand')}</p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>{t('acc.admin.username')}</span>
            <input className="acc-input" value={username} autoFocus autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.register.emailOptional')}</span>
            <input className="acc-input" type="email" value={email} autoComplete="email"
              onChange={(e) => setEmail(e.target.value)} />
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
              {busy ? t('acc.auth.register.submitBusy') : t('acc.auth.register.submit')}
            </button>
          </div>
          <p className="acc-sub" style={{ marginTop: 18, marginBottom: 0 }}>
            {t('acc.auth.register.haveAccountPrefix')}
            <Link to="/login">{t('acc.auth.register.haveAccountLink')}</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
