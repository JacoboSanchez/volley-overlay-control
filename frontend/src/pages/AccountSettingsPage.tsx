import { type FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import * as api from '../api/auth';
import { ApiError } from '../api/http';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n, LANGUAGE_NAMES } from '../i18n';
import { useAsyncAction } from '../hooks/useAsyncAction';
import { useToastAction } from '../hooks/useToastAction';

export default function AccountSettingsPage() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const { t, lang, setLanguage, languages } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const user = ctx?.user;

  const [displayName, setDisplayName] = useState(user?.display_name || '');
  const [email, setEmail] = useState(user?.email || '');

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
  // A mismatch is caught before the request, so it is the one password error
  // this component raises itself rather than reading off a response.
  const [pwMismatch, setPwMismatch] = useState('');

  const {
    run: saveProfile,
    pending: profileBusy,
    error: profileErr,
  } = useAsyncAction(
    async (e: FormEvent) => {
      e.preventDefault();
      await api.updateMe({ display_name: displayName, email });
      await refresh();
      // Success is transient (toast); the inline banner is for errors only.
      toast(t('acc.account.profileSaved'));
    },
    {
      formatError: (err) =>
        err instanceof ApiError && err.detail ? err.detail : t('acc.account.errorProfile'),
    },
  );

  const {
    run: runSavePassword,
    pending: pwBusy,
    error: pwRequestErr,
  } = useAsyncAction(
    async () => {
      await api.changePassword(current, next);
      setCurrent('');
      setNext('');
      setConfirmPw('');
      toast(t('acc.account.toastPasswordChanged'));
    },
    {
      formatError: (err) => {
        // 403 is specifically "the current password is wrong" — worth its own
        // copy, since the generic detail would not tell the user which field.
        if (err instanceof ApiError && err.status === 403) {
          return t('acc.account.errorWrongPassword');
        }
        if (err instanceof ApiError && err.detail) return err.detail;
        return t('acc.account.errorShortPassword');
      },
    },
  );
  const pwErr = pwMismatch || pwRequestErr;

  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPwMismatch('');
    if (next !== confirmPw) {
      setPwMismatch(t('acc.account.errorPasswordMismatch'));
      return;
    }
    await runSavePassword();
  }

  const { run: runDelete, pending: deleting } = useToastAction(async () => {
    await api.deleteMe();
    await refresh();
    navigate('/login');
  }, t('acc.account.errorDelete'));

  async function deleteAccount() {
    const ok = await confirm({
      title: t('acc.account.confirmDeleteTitle'),
      message: t('acc.account.confirmDeleteMsg'),
      confirmLabel: t('acc.account.confirmDeleteLabel'),
      danger: true,
    });
    if (!ok) return;
    await runDelete();
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
