import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

export default function LoginPage() {
  const { ctx, refresh } = useAuth();
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
    } catch {
      setError('Invalid username or password.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>Sign in</h1>
          <p className="acc-sub">Volley Overlay Control</p>
          {error && <div className="acc-error">{error}</div>}
          {ctx?.needs_admin_bootstrap && (
            <div className="acc-info">
              No administrator yet — <Link to="/claim-admin">claim the first admin</Link> using the
              token from the service startup log.
            </div>
          )}
          <label className="acc-field">
            <span>Username</span>
            <input
              className="acc-input"
              value={username}
              autoFocus
              autoComplete="username"
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label className="acc-field">
            <span>Password</span>
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
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </div>
          {ctx?.registration_open && (
            <p className="acc-sub" style={{ marginTop: 18, marginBottom: 0 }}>
              No account? <Link to="/register">Create one</Link>
            </p>
          )}
        </form>
      </div>
    </div>
  );
}
