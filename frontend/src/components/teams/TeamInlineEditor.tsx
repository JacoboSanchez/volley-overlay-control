import { useEffect, useRef, useState } from 'react';
import type * as api from '../../api/teams';
import { useI18n } from '../../i18n';
import { useToast } from '../Toast';
import TeamFieldset from './TeamFieldset';
import { useTeamDraft } from './useTeamDraft';
import { useToastAction } from '../../hooks/useToastAction';

/** The editor that drops inside a card when you tap Edit: the shared field set
 *  plus Save and (optionally) a destructive action. Seeded once from `team`, so
 *  in-progress edits survive a background list refresh without resetting. */
export default function TeamInlineEditor({
  team,
  onSave,
  onSaved,
  danger,
  iconPickerScope,
}: {
  team: api.TeamOut;
  onSave: (fields: api.TeamFields) => Promise<unknown>;
  onSaved: () => void;
  /** Optional destructive action rendered next to Save (delete / remove). */
  danger?: { label: string; onClick: () => void };
  iconPickerScope?: 'personal' | 'global';
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const draft = useTeamDraft(team);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      // onSaved() may collapse the row; don't leave the timer firing setState
      // on an unmounted editor (and don't stack timers on rapid saves).
      if (savedTimer.current) clearTimeout(savedTimer.current);
    },
    [],
  );

  const { run: runSave, pending: busy } = useToastAction(async () => {
    await onSave(draft.toFields());
    setSaved(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(false), 1200);
    onSaved();
    toast(t('acc.teams.toastSaved'));
  }, t('acc.teams.errorSave'));

  async function save() {
    if (!draft.name.trim() || busy) return;
    await runSave();
  }

  return (
    <>
      <TeamFieldset draft={draft} iconPickerScope={iconPickerScope} />
      <div className="acc-tcard__editor-actions">
        <button className="acc-btn" disabled={busy || !draft.name.trim()} onClick={save}>
          {saved ? t('acc.common.saved') : t('acc.common.save')}
        </button>
        {danger && (
          <button className="acc-btn danger" onClick={danger.onClick}>
            {danger.label}
          </button>
        )}
      </div>
    </>
  );
}
