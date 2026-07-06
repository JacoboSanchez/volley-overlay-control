import { FormEvent, useEffect, useState } from 'react';
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
  const [profileErr, setProfileErr] = useState('');
  const [profileBusy, setProfileBusy] = useState(false);

  // The auth context resolves asynchronously (and can refresh), so seed the
  // editable fields once the user lands / changes — useState only reads the
  // initial value.
  useEffect(() => {
    setDisplayName(user?.display_name || '');
    setEmail(user?.email || '');
  }, [user?.display_name, user?.email]);

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwErr, setPwErr] = useState('');
  const [pwBusy, setPwBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setProfileErr('');
    setProfileBusy(true);
    try {
      await api.updateMe({ display_name: displayName, email });
      await refresh();
      // Success is transient (toast); the inline banner is for errors only.
      toast(t('acc.account.profileSaved'));
    } catch (err) {
      setProfileErr(
        err instanceof api.ApiError && err.detail ? err.detail : t('acc.account.errorProfile'),
      );
    } finally {
      setProfileBusy(false);
    }
  }

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPwErr('');
    if (next !== confirmPw) {
      setPwErr(t('acc.account.errorPasswordMismatch'));
      return;
    }
    setPwBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirmPw('');
      toast(t('acc.account.toastPasswordChanged'));
    } catch (err) {
      if (err instanceof api.ApiError && err.status === 403) {
        setPwErr(t('acc.account.errorWrongPassword'));
      } else if (err instanceof api.ApiError && err.detail) {
        setPwErr(err.detail);
      } else {
        setPwErr(t('acc.account.errorShortPassword'));
      }
    } finally {
      setPwBusy(false);
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
    setDeleting(true);
    try {
      await api.deleteMe();
      await refresh();
      navigate('/login');
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.account.errorDelete'), 'error');
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <h2>{t('acc.nav.account')}</h2>

      <form onSubmit={saveProfile} className="acc-narrow" style={{ marginTop: 12 }}>
        <h3 className="acc-subhead">{t('acc.account.profile')}</h3>
        {profileErr && <div className="acc-error">{profileErr}</div>}
        <p className="acc-muted">
          {t('acc.account.username')} <strong>{user?.username}</strong>
        </p>
        <label className="acc-field">
          <span>{t('acc.account.displayName')}</span>
          <input
            className="acc-input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.email')}</span>
          <input
            className="acc-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <button className="acc-btn" type="submit" disabled={profileBusy}>
          {t('acc.account.saveProfile')}
        </button>
      </form>

      <form onSubmit={savePassword} className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.password')}</h3>
        {pwErr && <div className="acc-error">{pwErr}</div>}
        <label className="acc-field">
          <span>{t('acc.account.currentPassword')}</span>
          <input
            className="acc-input"
            type="password"
            value={current}
            autoComplete="current-password"
            onChange={(e) => setCurrent(e.target.value)}
          />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.newPassword')}</span>
          <input
            className="acc-input"
            type="password"
            value={next}
            autoComplete="new-password"
            onChange={(e) => setNext(e.target.value)}
          />
        </label>
        <label className="acc-field">
          <span>{t('acc.account.confirmPassword')}</span>
          <input
            className="acc-input"
            type="password"
            value={confirmPw}
            autoComplete="new-password"
            onChange={(e) => setConfirmPw(e.target.value)}
          />
        </label>
        <button className="acc-btn" type="submit" disabled={pwBusy}>
          {t('acc.account.password')}
        </button>
      </form>

      <div className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.preferences')}</h3>
        <label className="acc-field">
          <span>{t('acc.account.language')}</span>
          <select className="acc-input" value={lang} onChange={(e) => setLanguage(e.target.value)}>
            {languages.map((l) => (
              <option key={l} value={l}>
                {LANGUAGE_NAMES[l] ?? l}
              </option>
            ))}
          </select>
          <small className="acc-muted">{t('acc.account.languageDesc')}</small>
        </label>
      </div>

      <div className="acc-narrow" style={{ marginTop: 28 }}>
        <h3 className="acc-subhead">{t('acc.account.danger')}</h3>
        <p className="acc-muted">{t('acc.account.dangerDesc')}</p>
        <button className="acc-btn danger" onClick={deleteAccount} disabled={deleting}>
          {t('acc.account.deleteAccount')}
        </button>
      </div>
    </div>
  );
}
