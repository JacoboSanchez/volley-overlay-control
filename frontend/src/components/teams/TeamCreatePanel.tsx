import { FormEvent, useState } from 'react';
import * as api from '../../api/client';
import { useI18n } from '../../i18n';
import { useToast } from '../Toast';
import TeamFieldset from './TeamFieldset';
import { useTeamDraft } from './useTeamDraft';

/** Shared "create a team" form body (name / logo / colours + submit). The
 *  caller supplies the create call and the success message so the same panel
 *  drives both the user's custom teams and the admin catalog. */
export default function TeamCreatePanel({
  onCreate,
  onCreated,
  addLabel,
  successMessage,
  idPrefix,
  iconPickerScope,
}: {
  onCreate: (fields: api.TeamFields) => Promise<api.TeamOut>;
  onCreated: () => void;
  addLabel: string;
  successMessage: (name: string) => string;
  idPrefix?: string;
  iconPickerScope?: 'personal' | 'global';
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const draft = useTeamDraft();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!draft.name.trim() || busy) return;
    setError('');
    setBusy(true);
    try {
      const created = await onCreate(draft.toFields());
      draft.reset();
      onCreated();
      toast(successMessage(created.name));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.teams.errorCreate'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="acc-tcreate" onSubmit={submit}>
      <TeamFieldset draft={draft} idPrefix={idPrefix} iconPickerScope={iconPickerScope} />
      {error && (
        <div className="acc-error" style={{ marginTop: 10 }}>
          {error}
        </div>
      )}
      <div className="acc-tcreate__actions">
        <button className="acc-btn" type="submit" disabled={!draft.name.trim() || busy}>
          {addLabel}
        </button>
      </div>
    </form>
  );
}
