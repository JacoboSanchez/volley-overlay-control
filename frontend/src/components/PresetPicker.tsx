import { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../i18n';
import * as api from '../api/client';
import type { PresetOption } from '../api/client';
import type { ConfigModel } from './TeamCard';

const LAST_APPLIED_PREFIX = 'volley_last_preset:';

const SCOPE_KEY_BY_ID: Record<string, string> = {
  team_home: 'presets.scope.teamHome',
  team_away: 'presets.scope.teamAway',
  overlay_layout: 'presets.scope.layout',
  overlay_colors: 'presets.scope.colors',
  overlay_style: 'presets.scope.style',
  theme: 'presets.scope.theme',
};

function scopeLabel(scope: string, t: (key: string) => string): string {
  const key = SCOPE_KEY_BY_ID[scope];
  // Unknown scope: show the raw id rather than a translation key
  // (admin could add new scopes server-side faster than the frontend
  // i18n catalogue grows; better to render ``some_new_scope`` than the
  // literal ``presets.scope.some_new_scope`` placeholder).
  return key ? t(key) : scope;
}

function readLastApplied(oid: string): string | null {
  try {
    return window.localStorage.getItem(LAST_APPLIED_PREFIX + oid);
  } catch {
    return null;
  }
}

function writeLastApplied(oid: string, value: string): void {
  try {
    window.localStorage.setItem(LAST_APPLIED_PREFIX + oid, value);
  } catch {
    // private mode / quota — fall back silently; the pill will just
    // not survive a reload.
  }
}

export interface PresetPickerProps {
  oid: string;
  /**
   * Called with the flat-key patch the operator chose. The parent
   * deep-merges this into its in-memory edit ``model`` and marks the
   * panel dirty so the existing ``Save`` button persists the result —
   * same staging-then-save flow the rest of the panel uses.
   */
  onApplyPatch: (patch: ConfigModel) => void;
}

export default function PresetPicker({ oid, onApplyPatch }: PresetPickerProps) {
  const { t } = useI18n();
  const [items, setItems] = useState<PresetOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastApplied, setLastApplied] = useState<string | null>(() => readLastApplied(oid));

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getPresetOptions(oid)
      .then((data) => {
        if (cancelled) return;
        setItems(data.items || []);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : t('presets.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [oid, t]);

  useEffect(() => {
    setLastApplied(readLastApplied(oid));
  }, [oid]);

  const { predefined, yours } = useMemo(() => {
    const predef: PresetOption[] = [];
    const user: PresetOption[] = [];
    for (const it of items) {
      if (it.read_only) predef.push(it);
      else user.push(it);
    }
    return { predefined: predef, yours: user };
  }, [items]);

  function handleApply(item: PresetOption) {
    onApplyPatch(item.patch as ConfigModel);
    writeLastApplied(oid, item.id);
    setLastApplied(item.id);
  }

  if (loading) {
    return (
      <div className="preset-picker preset-picker-loading" data-testid="preset-picker">
        <span className="material-icons" aria-hidden="true">hourglass_top</span>
        {t('presets.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="preset-picker preset-picker-error" role="alert" data-testid="preset-picker">
        <span className="material-icons" aria-hidden="true">error_outline</span>
        {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="preset-picker preset-picker-empty" data-testid="preset-picker">
        <p className="preset-picker-empty-msg">{t('presets.empty')}</p>
        <p className="preset-picker-empty-hint">{t('presets.emptyHint')}</p>
      </div>
    );
  }

  return (
    <div className="preset-picker" data-testid="preset-picker">
      {lastApplied && (
        <div className="preset-picker-last" data-testid="preset-picker-last">
          <span className="material-icons" aria-hidden="true">history</span>
          {t('presets.lastApplied')}: {lastApplied}
        </div>
      )}

      {predefined.length > 0 && (
        <PresetGroup
          title={t('presets.predefined')}
          items={predefined}
          activeId={lastApplied}
          onApply={handleApply}
          testIdGroup="predefined"
        />
      )}

      {yours.length > 0 && (
        <PresetGroup
          title={t('presets.yours')}
          items={yours}
          activeId={lastApplied}
          onApply={handleApply}
          testIdGroup="yours"
        />
      )}
    </div>
  );
}

interface PresetGroupProps {
  title: string;
  items: PresetOption[];
  activeId: string | null;
  onApply: (item: PresetOption) => void;
  testIdGroup: string;
}

function PresetGroup({ title, items, activeId, onApply, testIdGroup }: PresetGroupProps) {
  const { t } = useI18n();
  return (
    <section className="preset-picker-group" data-testid={`preset-group-${testIdGroup}`}>
      <h4 className="preset-picker-group-title">{title}</h4>
      <ul className="preset-picker-list">
        {items.map((it) => {
          const active = activeId === it.id;
          return (
            <li
              key={it.id}
              className={`preset-picker-item ${active ? 'preset-picker-item-active' : ''}`}
              data-testid={`preset-item-${it.id}`}
            >
              <div className="preset-picker-item-head">
                <span className="preset-picker-item-name">{it.name}</span>
                {it.read_only && (
                  <span
                    className="preset-picker-readonly-badge"
                    title={t('presets.readOnlyHint')}
                  >
                    {t('presets.readOnlyBadge')}
                  </span>
                )}
              </div>
              <div className="preset-picker-scopes">
                {it.scopes.map((s) => (
                  <span key={s} className="preset-picker-scope-chip">
                    {scopeLabel(s, t)}
                  </span>
                ))}
              </div>
              <button
                type="button"
                className="preset-picker-apply-btn"
                onClick={() => onApply(it)}
                data-testid={`preset-apply-${it.id}`}
              >
                <span className="material-icons" aria-hidden="true">download</span>
                {t('presets.apply')}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
