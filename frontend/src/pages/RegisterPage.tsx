import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

export default function RegisterPage() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // Don't redirect silently when self-signup is off (or the app still needs its
  // first admin) — explain why and point the visitor at the right place.
  if (ctx && !ctx.registration_open) {
    return (
      <div className="acc-shell">
        <div className="acc-auth">
          <div className="acc-card">
            <h1>Sign-up disabled</h1>
            <p className="acc-sub">
              {ctx.needs_admin_bootstrap
                ? 'This instance has no administrator yet.'
                : 'Public registration is currently closed on this instance.'}
            </p>
            <div className="acc-info">
              {ctx.needs_admin_bootstrap ? (
                <>Set up the first account on the <Link to="/claim-admin">claim admin</Link> page using
                the token from the service startup log.</>
              ) : (
                <>Ask an administrator to create an account for you, then <Link to="/login">sign in</Link>.</>
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
    setBusy(true);
    try {
      await api.registerAccount(username.trim(), password, undefined, email.trim() || undefined);
      await refresh();
      navigate('/');
    } catch (err) {
      setError(err instanceof api.ApiError && err.status === 400
        ? 'That username or email is already taken, or the password is too short (min 8).'
        : 'Registration failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-shell">
      <div className="acc-auth">
        <form className="acc-card" onSubmit={onSubmit}>
          <h1>Create account</h1>
          <p className="acc-sub">Volley Overlay Control</p>
          {error && <div className="acc-error">{error}</div>}
          <label className="acc-field">
            <span>Username</span>
            <input className="acc-input" value={username} autoFocus
              onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>Email (optional)</span>
            <input className="acc-input" type="email" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="acc-field">
            <span>Password (min 8 characters)</span>
            <input className="acc-input" type="password" value={password}
              autoComplete="new-password" onChange={(e) => setPassword(e.target.value)} />
          </label>
          <div className="acc-btn-row">
            <button className="acc-btn" type="submit" disabled={busy}>
              {busy ? 'Creating…' : 'Create account'}
            </button>
          </div>
          <p className="acc-sub" style={{ marginTop: 18, marginBottom: 0 }}>
            Already have an account? <Link to="/login">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
