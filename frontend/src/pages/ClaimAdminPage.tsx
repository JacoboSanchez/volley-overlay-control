import { FormEvent, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

export default function ClaimAdminPage() {
  const { ctx, refresh } = useAuth();
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
      setError('Passwords do not match.');
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
          ? 'Invalid bootstrap token.'
          : 'Could not claim the administrator account.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>Claim first administrator</h1>
          <p className="acc-sub">
            Paste the one-time token printed in the service startup log on first run
            (<code>docker logs</code>, <code>journalctl</code>, or the console). It can also be set
            via the <code>ADMIN_BOOTSTRAP_TOKEN</code> environment variable, and is saved to
            <code>data/.admin_bootstrap_token</code>.
          </p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>Bootstrap token</span>
            <input className="acc-input" value={token} autoFocus autoComplete="off"
              onChange={(e) => setToken(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>Admin username</span>
            <input className="acc-input" value={username} autoComplete="username"
              onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>Password (min 8 characters)</span>
            <input className="acc-input" type="password" value={password}
              autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>Confirm password</span>
            <input className="acc-input" type="password" value={confirmPw}
              autoComplete="new-password" onChange={(e) => setConfirmPw(e.target.value)} />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? 'Claiming…' : 'Create administrator'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
