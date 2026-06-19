import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

/** Forced/standalone password change. Reachable while ``must_change_password``
 *  is set (the only guarded endpoints exempt during rotation are me/logout/
 *  change-password). */
export default function ChangePasswordPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await api.changePassword(current, next);
      await refresh();
      navigate('/');
    } catch (err) {
      setError(
        err instanceof api.ApiError && err.status === 403
          ? 'Current password is incorrect.'
          : 'Could not change the password (new password must be at least 8 characters).',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>Change your password</h1>
          <p className="acc-sub">You must set a new password before continuing.</p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>Current (or temporary) password</span>
            <input className="acc-input" type="password" value={current} autoFocus
              autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>New password (min 8 characters)</span>
            <input className="acc-input" type="password" value={next}
              autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? 'Saving…' : 'Set new password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
