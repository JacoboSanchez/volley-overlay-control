import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function AccountSettingsPage() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const user = ctx?.user;

  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [profileMsg, setProfileMsg] = useState('');

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [pwMsg, setPwMsg] = useState('');
  const [pwErr, setPwErr] = useState('');

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileMsg('');
    try {
      await api.updateMe({ display_name: displayName, email });
      await refresh();
      setProfileMsg('Profile saved.');
    } catch {
      setProfileMsg('Could not save profile (email may be taken).');
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPwMsg('');
    setPwErr('');
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setPwMsg('Password changed. Other sessions were signed out.');
    } catch (err) {
      setPwErr(
        err instanceof api.ApiError && err.status === 403
          ? 'Current password is incorrect.'
          : 'New password must be at least 8 characters.',
      );
    }
  }

  async function deleteAccount() {
    if (!confirm('Delete your account? This permanently removes your overlays, teams, presets and reports.')) return;
    await api.deleteMe();
    await refresh();
    navigate('/login');
  }

  return (
    <div>
      <h2>Account</h2>

      <form onSubmit={saveProfile} style={{ maxWidth: 420, marginTop: 12 }}>
        <h3>Profile</h3>
        {profileMsg && <div className="acc-info">{profileMsg}</div>}
        <p className="acc-muted">Username: <strong>{user?.username}</strong></p>
        <label className="acc-field">
          <span>Display name</span>
          <input className="acc-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>Email</span>
          <input className="acc-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit">Save profile</button>
      </form>

      <form onSubmit={savePassword} style={{ maxWidth: 420, marginTop: 28 }}>
        <h3>Change password</h3>
        {pwMsg && <div className="acc-info">{pwMsg}</div>}
        {pwErr && <div className="acc-error">{pwErr}</div>}
        <label className="acc-field">
          <span>Current password</span>
          <input className="acc-input" type="password" value={current}
            autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>New password (min 8)</span>
          <input className="acc-input" type="password" value={next}
            autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit">Change password</button>
      </form>

      <div style={{ maxWidth: 420, marginTop: 28 }}>
        <h3>Danger zone</h3>
        <p className="acc-muted">Permanently delete your account and all its data.</p>
        <button className="acc-btn danger" onClick={deleteAccount}>Delete my account</button>
      </div>
    </div>
  );
}
