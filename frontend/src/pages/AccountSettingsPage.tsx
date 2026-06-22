import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';

export default function AccountSettingsPage() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const confirm = useConfirm();
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
      toast('Profile saved.');
    } catch (err) {
      setProfileMsg(
        err instanceof api.ApiError && err.detail
          ? err.detail
          : 'Could not save profile (email may be taken).',
      );
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
      toast('Password changed.');
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 403) {
        setPwErr('Current password is incorrect.');
      } else if (err instanceof api.ApiError && err.detail) {
        setPwErr(err.detail);
      } else {
        setPwErr('New password must be at least 8 characters.');
      }
    }
  }

  async function deleteAccount() {
    const ok = await confirm({
      title: 'Delete account',
      message: 'Delete your account? This permanently removes your overlays, teams, presets and reports.',
      confirmLabel: 'Delete account',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteMe();
      await refresh();
      navigate('/login');
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : 'Could not delete account.', 'error');
    }
  }

  return (
    <div>
      <h2>Account</h2>

      <form onSubmit={saveProfile} className="acc-narrow" style={{ marginTop: 12 }}>
        <h3 className="acc-subhead">Profile</h3>
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

      <form onSubmit={savePassword} className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">Change password</h3>
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

      <div className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">Danger zone</h3>
        <p className="acc-muted">Permanently delete your account and all its data.</p>
        <button className="acc-btn danger" onClick={deleteAccount}>Delete my account</button>
      </div>
    </div>
  );
}
