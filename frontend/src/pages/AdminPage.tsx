import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';

export default function AdminPage() {
  const { ctx } = useAuth();
  const [users, setUsers] = useState<api.UserOut[]>([]);
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');
  const [tempNotice, setTempNotice] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([api.adminListUsers(), api.adminGetRegistration()]);
      setUsers(u);
      setRegistrationOpen(r.registration_open);
    } catch {
      setError('Could not load admin data.');
    }
  }, []);

  // Only fire admin-only calls for an admin: a non-admin who reaches this URL
  // is redirected below, so we must not request /admin/* (avoids 403 noise).
  useEffect(() => {
    if (ctx?.user?.role === 'admin') void load();
  }, [load, ctx]);

  if (ctx && ctx.user?.role !== 'admin') return <Navigate to="/" replace />;

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError('');
    setTempNotice('');
    try {
      const res = await api.adminCreateUser(newName.trim(), { role: newRole });
      setNewName('');
      setTempNotice(`Created "${res.user.username}". Temporary password: ${res.temp_password}`);
      await load();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Could not create user.');
    }
  }

  async function resetPw(u: api.UserOut) {
    setError('');
    try {
      const res = await api.adminResetPassword(u.id);
      setTempNotice(`Reset "${u.username}". Temporary password: ${res.temp_password}`);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Password reset failed.');
    }
  }

  async function toggleActive(u: api.UserOut) {
    try {
      await api.adminUpdateUser(u.id, { is_active: !u.is_active });
      await load();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Update failed.');
    }
  }

  async function del(u: api.UserOut) {
    if (!confirm(`Delete user "${u.username}"?`)) return;
    try {
      await api.adminDeleteUser(u.id);
      await load();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Delete failed.');
    }
  }

  async function toggleRegistration() {
    setError('');
    try {
      const r = await api.adminSetRegistration(!registrationOpen);
      setRegistrationOpen(r.registration_open);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : 'Could not change the registration setting.');
      await load(); // re-sync the label to the authoritative value
    }
  }

  // Guard the destructive controls on the sole remaining admin (the backend
  // also enforces this; the UI just avoids a surprising post-hoc error).
  const activeAdminCount = users.filter((u) => u.role === 'admin' && u.is_active).length;

  return (
    <div>
      <h2>Administration</h2>

      <div className="acc-row" style={{ marginTop: 8 }}>
        <span>Public registration is <strong>{registrationOpen ? 'open' : 'closed'}</strong>.</span>
        <button className="acc-btn secondary" onClick={toggleRegistration}>
          {registrationOpen ? 'Close registration' : 'Open registration'}
        </button>
      </div>

      {tempNotice && <div className="acc-info">{tempNotice}</div>}
      {error && <div className="acc-error">{error}</div>}

      <h3 className="acc-subhead">Create user</h3>
      <form className="acc-row" onSubmit={createUser}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Username</span>
          <input className="acc-input" value={newName} onChange={(e) => setNewName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>Role</span>
          <select className="acc-input" value={newRole} onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}>
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <button className="acc-btn" type="submit" disabled={!newName.trim()}>Create (temp password)</button>
      </form>

      <h3 className="acc-subhead">Users</h3>
      <table className="acc-table">
        <thead><tr><th>Username</th><th>Role</th><th>Active</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => {
            const isSelf = ctx?.user?.id === u.id;
            const lockLastAdmin = u.role === 'admin' && u.is_active && activeAdminCount <= 1;
            const lockTitle = lockLastAdmin ? 'The last active administrator cannot be removed.' : undefined;
            return (
              <tr key={u.id}>
                <td>
                  {u.username}
                  {isSelf && <span className="acc-muted"> (you)</span>}
                  {u.must_change_password && <span className="acc-pill" style={{ marginLeft: 6 }}>must change pw</span>}
                </td>
                <td>{u.role}</td>
                <td>{u.is_active ? 'yes' : 'no'}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="acc-btn ghost" onClick={() => resetPw(u)}>Reset pw</button>{' '}
                  <button className="acc-btn ghost" onClick={() => toggleActive(u)}
                    disabled={lockLastAdmin} title={lockTitle}>
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>{' '}
                  <button className="acc-btn danger" onClick={() => del(u)}
                    disabled={lockLastAdmin} title={lockTitle}>Delete</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
