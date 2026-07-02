import { useEffect, useState } from 'react';
import { useI18n } from '../../i18n';
import * as api from '../../api/client';
import { useAsyncAction } from '../../hooks/useAsyncAction';
import { InstantHint } from './fields';

export interface MatchRulesSectionProps {
  oid: string;
  /**
   * Live values pulled from ``state.config``. The component renders
   * controlled inputs around them, so it always reflects what the
   * server reports. ``null`` means "still loading" — the section
   * shows a placeholder.
   */
  mode: api.MatchMode | null;
  pointsLimit: number | null;
  pointsLimitLastSet: number | null;
  setsLimit: number | null;
  /** Live ``state.auto_swap_sides``; ``null`` while loading. */
  autoSwapSides?: boolean | null;
  /** Called after a successful update so the parent refreshes state. */
  onChanged?: () => void;
}

const MODE_PRESETS: Record<
  api.MatchMode,
  {
    points_limit: number;
    points_limit_last_set: number;
    sets_limit: number;
  }
> = {
  indoor: { points_limit: 25, points_limit_last_set: 15, sets_limit: 5 },
  beach: { points_limit: 21, points_limit_last_set: 15, sets_limit: 3 },
  table_tennis: { points_limit: 11, points_limit_last_set: 11, sets_limit: 5 },
};

const SETS_OPTIONS = [1, 3, 5, 7];

const MODE_ICONS: Record<api.MatchMode, string> = {
  indoor: 'sports_volleyball',
  beach: 'beach_access',
  table_tennis: 'sports_tennis',
};

export default function MatchRulesSection({
  oid,
  mode,
  pointsLimit,
  pointsLimitLastSet,
  setsLimit,
  autoSwapSides = null,
  onChanged,
}: MatchRulesSectionProps) {
  const { t } = useI18n();
  const [pointsDraft, setPointsDraft] = useState<number | null>(pointsLimit);
  const [pointsLastDraft, setPointsLastDraft] = useState<number | null>(pointsLimitLastSet);
  const [pointsError, setPointsError] = useState<string | null>(null);

  useEffect(() => {
    setPointsDraft(pointsLimit);
  }, [pointsLimit]);
  useEffect(() => {
    setPointsLastDraft(pointsLimitLastSet);
  }, [pointsLimitLastSet]);

  const {
    run: call,
    pending,
    error,
  } = useAsyncAction<[api.SetRulesPayload]>(async (payload) => {
    await api.setRules(oid, payload);
    onChanged?.();
  });

  function handleModeChange(newMode: api.MatchMode) {
    if (newMode === mode) return;
    // Switching mode is the natural moment to apply the preset's
    // defaults — prevents stale 25-point limits stuck on a beach
    // match. Operators can still override per-field below.
    void call({ mode: newMode, reset_to_defaults: true });
  }

  function handleSetsChange(value: number) {
    if (value === setsLimit) return;
    void call({ sets_limit: value });
  }

  function handlePointsCommit(field: 'points_limit' | 'points_limit_last_set', value: number) {
    if (Number.isNaN(value) || value <= 0) {
      // Tell the operator why nothing changed instead of silently
      // reverting on the next state refresh.
      setPointsError(t('rules.invalidPoints'));
      return;
    }
    setPointsError(null);
    if (field === 'points_limit' && value === pointsLimit) return;
    if (field === 'points_limit_last_set' && value === pointsLimitLastSet) return;
    void call({ [field]: value });
  }

  function handleResetDefaults() {
    if (mode === null) return;
    void call({ mode, reset_to_defaults: true });
  }

  if (mode === null || pointsLimit === null || pointsLimitLastSet === null || setsLimit === null) {
    return (
      <div className="config-section-rules">
        <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
          {t('rules.loading')}
        </p>
      </div>
    );
  }

  const preset = MODE_PRESETS[mode];
  const isAtDefaults =
    pointsLimit === preset.points_limit &&
    pointsLimitLastSet === preset.points_limit_last_set &&
    setsLimit === preset.sets_limit;

  return (
    <div className="config-section-rules">
      <InstantHint />
      <label className="config-label">{t('rules.mode')}</label>
      <div
        className="config-mode-toggle"
        role="radiogroup"
        aria-label={t('rules.mode')}
        data-testid="rules-mode-toggle"
      >
        {(['indoor', 'beach', 'table_tennis'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={mode === m}
            className={`config-mode-toggle-btn ${mode === m ? 'config-mode-toggle-btn-active' : ''}`}
            onClick={() => handleModeChange(m)}
            disabled={pending}
            data-testid={`rules-mode-${m}`}
          >
            <span className="material-icons">{MODE_ICONS[m]}</span>
            {t(`rules.mode.${m}`)}
          </button>
        ))}
      </div>

      <label className="config-switch-label config-auto-swap-row">
        <input
          type="checkbox"
          checked={autoSwapSides ?? false}
          disabled={autoSwapSides === null || pending}
          onChange={(e) => {
            void (async () => {
              try {
                await api.setAutoSwapSides(oid, e.target.checked);
                onChanged?.();
              } catch {
                /* surfaced by the next state poll */
              }
            })();
          }}
          data-testid="rules-auto-swap-sides"
        />
        {t('rules.autoSwapSides')}
      </label>
      <p className="config-hint">{t('rules.autoSwapSidesHint')}</p>

      <div className="config-separator" />

      <label className="config-label" htmlFor="rules-sets">
        {t('rules.setsLimit')}
      </label>
      <select
        id="rules-sets"
        className="config-select"
        value={setsLimit}
        onChange={(e) => handleSetsChange(parseInt(e.target.value, 10))}
        disabled={pending}
        data-testid="rules-sets-select"
      >
        {SETS_OPTIONS.map((opt) => (
          <option key={opt} value={opt}>
            {t(`rules.bestOf.${opt}`)}
          </option>
        ))}
      </select>

      {setsLimit === 1 ? (
        // Best-of-1: the only set IS also the deciding set, so two
        // separate "Points / set" and "Points / final set" inputs
        // would be confusing. We show a single input and on commit
        // dispatch both fields so the server stays consistent —
        // ``GameManager.add_game`` uses ``points_limit_last_set``
        // when ``current_set == sets_limit``, but mirroring the
        // value to ``points_limit`` too means switching back to a
        // best-of-3/5 later starts from sensible matching defaults.
        <div className="config-stepper-grid">
          <div className="config-stepper-group">
            <label className="config-label" htmlFor="rules-points">
              {t('rules.pointsLimit')}
            </label>
            <input
              id="rules-points"
              type="number"
              className="config-stepper-input"
              min={1}
              max={99}
              value={pointsLastDraft ?? ''}
              onChange={(e) => {
                setPointsError(null);
                setPointsLastDraft(parseInt(e.target.value, 10));
              }}
              onBlur={() => {
                if (
                  pointsLastDraft === null ||
                  Number.isNaN(pointsLastDraft) ||
                  pointsLastDraft <= 0
                ) {
                  setPointsError(t('rules.invalidPoints'));
                  return;
                }
                setPointsError(null);
                if (pointsLastDraft !== pointsLimitLastSet || pointsLastDraft !== pointsLimit) {
                  void call({
                    points_limit: pointsLastDraft,
                    points_limit_last_set: pointsLastDraft,
                  });
                }
              }}
              disabled={pending}
              data-testid="rules-points-input"
            />
          </div>
        </div>
      ) : (
        <div className="config-stepper-grid">
          <div className="config-stepper-group">
            <label className="config-label" htmlFor="rules-points">
              {t('rules.pointsLimit')}
            </label>
            <input
              id="rules-points"
              type="number"
              className="config-stepper-input"
              min={1}
              max={99}
              value={pointsDraft ?? ''}
              onChange={(e) => {
                setPointsError(null);
                setPointsDraft(parseInt(e.target.value, 10));
              }}
              onBlur={() => pointsDraft !== null && handlePointsCommit('points_limit', pointsDraft)}
              disabled={pending}
              data-testid="rules-points-input"
            />
          </div>
          <div className="config-stepper-group">
            <label className="config-label" htmlFor="rules-points-last">
              {t('rules.pointsLimitLastSet')}
            </label>
            <input
              id="rules-points-last"
              type="number"
              className="config-stepper-input"
              min={1}
              max={99}
              value={pointsLastDraft ?? ''}
              onChange={(e) => {
                setPointsError(null);
                setPointsLastDraft(parseInt(e.target.value, 10));
              }}
              onBlur={() =>
                pointsLastDraft !== null &&
                handlePointsCommit('points_limit_last_set', pointsLastDraft)
              }
              disabled={pending}
              data-testid="rules-points-last-input"
            />
          </div>
        </div>
      )}

      {pointsError && (
        <p className="config-hint config-field-error" role="alert" data-testid="rules-points-error">
          {pointsError}
        </p>
      )}

      <button
        type="button"
        className="config-inline-btn"
        onClick={handleResetDefaults}
        disabled={pending || isAtDefaults}
        data-testid="rules-reset-defaults"
      >
        <span className="material-icons">restart_alt</span>
        {t('rules.resetDefaults')}
      </button>

      {error && (
        <p className="config-save-error" style={{ position: 'static', marginTop: '0.5rem' }}>
          {error}
        </p>
      )}
    </div>
  );
}
