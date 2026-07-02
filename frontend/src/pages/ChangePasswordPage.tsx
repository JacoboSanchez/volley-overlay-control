import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import './account.css';

/** Forced/standalone password change. Reachable while ``must_change_password``
 *  is set (the only guarded endpoints exempt during rotation are me/logout/
 *  change-password). */
export default function ChangePasswordPage() {
  const { refresh } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    if (next !== confirmPw) {
      setError(t('acc.account.errorPasswordMismatch'));
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      await refresh();
      navigate('/');
    } catch (err) {
      setError(
        err instanceof api.ApiError && err.status === 403
          ? t('acc.account.errorWrongPassword')
          : t('acc.auth.changePw.errorFailed'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>{t('acc.auth.changePw.title')}</h1>
          <p className="acc-sub">{t('acc.auth.changePw.subtitle')}</p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>{t('acc.auth.changePw.currentLabel')}</span>
            <input className="acc-input" type="password" value={current} autoFocus
              autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.auth.changePw.newLabel')}</span>
            <input className="acc-input" type="password" value={next}
              autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>{t('acc.account.confirmPassword')}</span>
            <input className="acc-input" type="password" value={confirmPw}
              autoComplete="new-password" onChange={(e) => setConfirmPw(e.target.value)} />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? t('acc.auth.changePw.submitBusy') : t('acc.auth.changePw.submit')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
