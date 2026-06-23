import { FormEvent, useCallback, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import CopyField from '../components/CopyField';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';

export default function AdminPage() {
  const { ctx } = useAuth();
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [users, setUsers] = useState<api.UserOut[]>([]);
  const [registrationOpen, setRegistrationOpen] = useState(true);
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');
  const [tempCred, setTempCred] = useState<{ text: string; password: string } | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [u, r] = await Promise.all([api.adminListUsers(), api.adminGetRegistration()]);
      setUsers(u);
      setRegistrationOpen(r.registration_open);
    } catch {
      setError(t('acc.admin.errorLoad'));
    }
  }, [t]);

  // Only fire admin-only calls for an admin: a non-admin who reaches this URL
  // is redirected below, so we must not request /admin/* (avoids 403 noise).
  useEffect(() => {
    if (ctx?.user?.role === 'admin') void load();
  }, [load, ctx]);

  if (ctx && ctx.user?.role !== 'admin') return <Navigate to="/" replace />;

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError('');
    setTempCred(null);
    try {
      const res = await api.adminCreateUser(newName.trim(), { role: newRole });
      setNewName('');
      setTempCred({ text: t('acc.admin.created', { username: res.user.username }), password: res.temp_password });
      await load();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.admin.errorCreate'));
    }
  }

  async function resetPw(u: api.UserOut) {
    setError('');
    try {
      const res = await api.adminResetPassword(u.id);
      setTempCred({ text: t('acc.admin.reset', { username: u.username }), password: res.temp_password });
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.admin.errorReset'));
    }
  }

  async function toggleActive(u: api.UserOut) {
    try {
      await api.adminUpdateUser(u.id, { is_active: !u.is_active });
      await load();
      toast(u.is_active
        ? t('acc.admin.toastDeactivated', { username: u.username })
        : t('acc.admin.toastActivated', { username: u.username }));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.admin.errorUpdate'));
    }
  }

  async function del(u: api.UserOut) {
    const ok = await confirm({
      title: t('acc.admin.confirmDeleteTitle'),
      message: t('acc.admin.confirmDeleteMsg', { username: u.username }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteUser(u.id);
      await load();
      toast(t('acc.admin.toastDeleted', { username: u.username }));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.admin.errorDelete'));
    }
  }

  async function toggleRegistration() {
    setError('');
    try {
      const r = await api.adminSetRegistration(!registrationOpen);
      setRegistrationOpen(r.registration_open);
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.admin.errorRegistration'));
      await load(); // re-sync the label to the authoritative value
    }
  }

  // Guard the destructive controls on the sole remaining admin (the backend
  // also enforces this; the UI just avoids a surprising post-hoc error).
  const activeAdminCount = users.filter((u) => u.role === 'admin' && u.is_active).length;

  return (
    <div>
      <h2>{t('acc.admin.title')}</h2>

      <div className="acc-row" style={{ marginTop: 8 }}>
        <span>{registrationOpen ? t('acc.admin.registrationOpen') : t('acc.admin.registrationClosed')}</span>
        <button className="acc-btn secondary" onClick={toggleRegistration}>
          {registrationOpen ? t('acc.admin.closeRegistration') : t('acc.admin.openRegistration')}
        </button>
      </div>

      {tempCred && (
        <div className="acc-info">
          <div>{tempCred.text}</div>
          <div style={{ marginTop: 8 }}>
            <CopyField value={tempCred.password} label={t('acc.admin.tempPassword')} />
          </div>
          <div className="acc-muted" style={{ marginTop: 6 }}>{t('acc.admin.tempHint')}</div>
        </div>
      )}
      {error && <div className="acc-error">{error}</div>}

      <h3 className="acc-subhead">{t('acc.admin.createUser')}</h3>
      <form className="acc-row" onSubmit={createUser}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.admin.username')}</span>
          <input className="acc-input" value={newName} onChange={(e) => setNewName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.admin.role')}</span>
          <select className="acc-input" value={newRole} onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}>
            <option value="user">{t('acc.admin.roleUser')}</option>
            <option value="admin">{t('acc.admin.roleAdmin')}</option>
          </select>
        </label>
        <button className="acc-btn" type="submit" disabled={!newName.trim()}>{t('acc.admin.createBtn')}</button>
      </form>

      <h3 className="acc-subhead">{t('acc.admin.users')}</h3>
      <table className="acc-table">
        <thead><tr>
          <th scope="col">{t('acc.admin.colUsername')}</th><th scope="col">{t('acc.admin.colRole')}</th>
          <th scope="col">{t('acc.admin.colActive')}</th><th scope="col"></th>
        </tr></thead>
        <tbody>
          {users.map((u) => {
            const isSelf = ctx?.user?.id === u.id;
            const lockLastAdmin = u.role === 'admin' && u.is_active && activeAdminCount <= 1;
            const lockTitle = lockLastAdmin ? t('acc.admin.lockLastAdmin') : undefined;
            return (
              <tr key={u.id}>
                <td>
                  {u.username}
                  {isSelf && <span className="acc-muted"> {t('acc.admin.you')}</span>}
                  {u.must_change_password && <span className="acc-pill" style={{ marginLeft: 6 }}>{t('acc.admin.mustChangePw')}</span>}
                </td>
                <td data-label={t('acc.admin.colRole')}>{u.role}</td>
                <td data-label={t('acc.admin.colActive')}>{u.is_active ? t('acc.admin.yes') : t('acc.admin.no')}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="acc-btn ghost" onClick={() => resetPw(u)}>{t('acc.admin.resetPw')}</button>{' '}
                  <button className="acc-btn ghost" onClick={() => toggleActive(u)}
                    disabled={lockLastAdmin} title={lockTitle}>
                    {u.is_active ? t('acc.admin.deactivate') : t('acc.admin.activate')}
                  </button>{' '}
                  <button className="acc-btn danger" onClick={() => del(u)}
                    disabled={lockLastAdmin} title={lockTitle}>{t('acc.common.delete')}</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
