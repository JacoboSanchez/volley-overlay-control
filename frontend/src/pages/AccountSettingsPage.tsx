import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n, LANGUAGE_NAMES } from '../i18n';

export default function AccountSettingsPage() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const { t, lang, setLanguage, languages } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const user = ctx?.user;

  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [profileMsg, setProfileMsg] = useState('');

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwMsg, setPwMsg] = useState('');
  const [pwErr, setPwErr] = useState('');

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileMsg('');
    try {
      await api.updateMe({ display_name: displayName, email });
      await refresh();
      setProfileMsg(t('acc.account.profileSaved'));
      toast(t('acc.account.profileSaved'));
    } catch (err) {
      setProfileMsg(
        err instanceof api.ApiError && err.detail
          ? err.detail
          : t('acc.account.errorProfile'),
      );
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPwMsg('');
    setPwErr('');
    if (next !== confirmPw) {
      setPwErr(t('acc.account.errorPasswordMismatch'));
      return;
    }
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirmPw('');
      setPwMsg(t('acc.account.passwordChanged'));
      toast(t('acc.account.toastPasswordChanged'));
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 403) {
        setPwErr(t('acc.account.errorWrongPassword'));
      } else if (err instanceof api.ApiError && err.detail) {
        setPwErr(err.detail);
      } else {
        setPwErr(t('acc.account.errorShortPassword'));
      }
    }
  }

  async function deleteAccount() {
    const ok = await confirm({
      title: t('acc.account.confirmDeleteTitle'),
      message: t('acc.account.confirmDeleteMsg'),
      confirmLabel: t('acc.account.confirmDeleteLabel'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deleteMe();
      await refresh();
      navigate('/login');
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.account.errorDelete'), 'error');
    }
  }

  return (
    <div>
      <h2>{t('acc.nav.account')}</h2>

      <form onSubmit={saveProfile} className="acc-narrow" style={{ marginTop: 12 }}>
        <h3 className="acc-subhead">{t('acc.account.profile')}</h3>
        {profileMsg && <div className="acc-info">{profileMsg}</div>}
        <p className="acc-muted">{t('acc.account.username')} <strong>{user?.username}</strong></p>
        <label className="acc-field">
          <span>{t('acc.account.displayName')}</span>
          <input className="acc-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.email')}</span>
          <input className="acc-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit">{t('acc.account.saveProfile')}</button>
      </form>

      <form onSubmit={savePassword} className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.password')}</h3>
        {pwMsg && <div className="acc-info">{pwMsg}</div>}
        {pwErr && <div className="acc-error">{pwErr}</div>}
        <label className="acc-field">
          <span>{t('acc.account.currentPassword')}</span>
          <input className="acc-input" type="password" value={current}
            autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.newPassword')}</span>
          <input className="acc-input" type="password" value={next}
            autoComplete="new-password" onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.confirmPassword')}</span>
          <input className="acc-input" type="password" value={confirmPw}
            autoComplete="new-password" onChange={(e) => setConfirmPw(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit">{t('acc.account.password')}</button>
      </form>

      <div className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.preferences')}</h3>
        <label className="acc-field">
          <span>{t('acc.account.language')}</span>
          <select className="acc-input" value={lang} onChange={(e) => setLanguage(e.target.value)}>
            {languages.map((l) => (
              <option key={l} value={l}>{LANGUAGE_NAMES[l] ?? l}</option>
            ))}
          </select>
          <small className="acc-muted">{t('acc.account.languageDesc')}</small>
        </label>
      </div>

      <div className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.danger')}</h3>
        <p className="acc-muted">{t('acc.account.dangerDesc')}</p>
        <button className="acc-btn danger" onClick={deleteAccount}>{t('acc.account.deleteAccount')}</button>
      </div>
    </div>
  );
}
