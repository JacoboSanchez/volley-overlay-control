import { useCallback, useEffect, useMemo, useState } from 'react';
import { useI18n } from '../i18n';
import * as api from '../api/client';
import type { PresetSummary } from '../api/client';
import type { ConfigModel } from './TeamCard';

const CATEGORY_ORDER = [
  'team1_name',
  'team1_color',
  'team2_name',
  'team2_color',
  'position',
  'style',
] as const;
type CategoryId = (typeof CATEGORY_ORDER)[number];

const CATEGORY_LABEL_KEY: Record<CategoryId, string> = {
  team1_name: 'presets.cat.team1Name',
  team1_color: 'presets.cat.team1Color',
  team2_name: 'presets.cat.team2Name',
  team2_color: 'presets.cat.team2Color',
  position: 'presets.cat.position',
  style: 'presets.cat.style',
};

const CATEGORY_ICON: Record<CategoryId, string> = {
  team1_name: 'badge',
  team1_color: 'palette',
  team2_name: 'badge',
  team2_color: 'palette',
  position: 'open_with',
  style: 'view_quilt',
};

// Mirrors ``app/api/preset_categories.py``. Both ends drift in lockstep
// with ``ALLOWED_CUSTOMIZATION_KEYS``; the backend rejects unknown
// keys at create time so a stale catalogue here is annoying but safe.
const KEYS_BY_CATEGORY: Record<CategoryId, readonly string[]> = {
  team1_name: ['Team 1 Name', 'Team 1 Text Name'],
  team1_color: ['Team 1 Color', 'Team 1 Text Color', 'Team 1 Logo'],
  team2_name: ['Team 2 Name', 'Team 2 Text Name'],
  team2_color: ['Team 2 Color', 'Team 2 Text Color', 'Team 2 Logo'],
  position: ['Height', 'Width', 'Left-Right', 'Up-Down'],
  style: [
    'preferredStyle',
    'Logos',
    'Gradient',
    'Show Stats',
    'Show Points History',
    'Color 1',
    'Color 2',
    'Text Color 1',
    'Text Color 2',
  ],
};

function categoryLabel(id: string, t: (key: string) => string): string {
  const key = CATEGORY_LABEL_KEY[id as CategoryId];
  return key ? t(key) : id;
}

function categoryIcon(id: string): string {
  return CATEGORY_ICON[id as CategoryId] ?? 'tune';
}

export interface PresetPickerProps {
  /**
   * The operator's current edit model. Used as the source for "Save
   * current configuration" — only the keys belonging to the picked
   * categories are sent to the server.
   */
  model: ConfigModel;
  /**
   * Called with the flat-key patch the operator chose. The parent
   * deep-merges this into its in-memory edit ``model`` and marks the
   * panel dirty so the existing ``Save`` button persists the result.
   */
  onApplyPatch: (patch: ConfigModel) => void;
}

export default function PresetPicker({ model, onApplyPatch }: PresetPickerProps) {
  const { t } = useI18n();
  const [items, setItems] = useState<PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  // Create form state
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createCats, setCreateCats] = useState<Set<CategoryId>>(
    () => new Set<CategoryId>(),
  );
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listPresets();
      setItems(data.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('presets.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function toggleCat(id: CategoryId) {
    setCreateCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setActionError(null);
    const name = createName.trim();
    if (!name) {
      setActionError(t('presets.nameRequired'));
      return;
    }
    if (createCats.size === 0) {
      setActionError(t('presets.pickAtLeastOne'));
      return;
    }
    const values: Record<string, unknown> = {};
    for (const cat of createCats) {
      for (const key of KEYS_BY_CATEGORY[cat]) {
        if (key in model) {
          values[key] = (model as Record<string, unknown>)[key];
        }
      }
    }
    if (Object.keys(values).length === 0) {
      setActionError(t('presets.noValuesForCategories'));
      return;
    }
    setCreating(true);
    try {
      await api.createPreset(name, values);
      setCreateOpen(false);
      setCreateName('');
      setCreateCats(new Set());
      await refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t('presets.saveFailed'));
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(slug: string) {
    setActionError(null);
    setPendingDelete(slug);
    try {
      await api.deletePreset(slug);
      await refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t('presets.deleteFailed'));
    } finally {
      setPendingDelete(null);
    }
  }

  function handleApply(item: PresetSummary) {
    onApplyPatch(item.values as ConfigModel);
  }

  // System presets first, then user presets — both alphabetised. The
  // backend already returns them in this order, but re-sorting client
  // side keeps the picker stable if a future endpoint change reorders
  // them.
  const sortedItems = useMemo(
    () =>
      [...items].sort((a, b) => {
        if (a.source !== b.source) return a.source === 'system' ? -1 : 1;
        return a.name.localeCompare(b.name);
      }),
    [items],
  );

  return (
    <div className="preset-picker" data-testid="preset-picker">
      <div className="preset-picker-toolbar">
        <button
          type="button"
          className="preset-picker-create-toggle"
          onClick={() => {
            setCreateOpen((open) => !open);
            setActionError(null);
          }}
          data-testid="preset-create-toggle"
          aria-expanded={createOpen}
        >
          <span className="material-icons" aria-hidden="true">
            {createOpen ? 'close' : 'add'}
          </span>
          {createOpen ? t('presets.cancel') : t('presets.saveCurrent')}
        </button>
      </div>

      {createOpen && (
        <form
          className="preset-picker-create"
          onSubmit={handleCreate}
          data-testid="preset-create-form"
        >
          <label className="preset-picker-label">
            {t('presets.name')}
            <input
              className="preset-picker-input"
              type="text"
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
              maxLength={120}
              data-testid="preset-create-name"
              autoFocus
            />
          </label>

          <fieldset className="preset-picker-fieldset">
            <legend>{t('presets.includeCategories')}</legend>
            {CATEGORY_ORDER.map((cat) => (
              <label key={cat} className="preset-picker-cat-toggle">
                <input
                  type="checkbox"
                  checked={createCats.has(cat)}
                  onChange={() => toggleCat(cat)}
                  data-testid={`preset-create-cat-${cat}`}
                />
                <span className="material-icons" aria-hidden="true">
                  {categoryIcon(cat)}
                </span>
                {categoryLabel(cat, t)}
              </label>
            ))}
          </fieldset>

          <div className="preset-picker-actions">
            <button
              type="submit"
              className="preset-picker-confirm-btn"
              disabled={creating}
              data-testid="preset-create-submit"
            >
              {creating ? t('presets.saving') : t('presets.save')}
            </button>
          </div>
        </form>
      )}

      {actionError && (
        <div
          className="preset-picker-action-error"
          role="alert"
          data-testid="preset-action-error"
        >
          <span className="material-icons" aria-hidden="true">error_outline</span>
          {actionError}
        </div>
      )}

      {loading ? (
        <div className="preset-picker-loading" data-testid="preset-picker-loading">
          <span className="material-icons" aria-hidden="true">hourglass_top</span>
          {t('presets.loading')}
        </div>
      ) : error ? (
        <div
          className="preset-picker-error"
          role="alert"
          data-testid="preset-picker-error"
        >
          <span className="material-icons" aria-hidden="true">error_outline</span>
          {error}
        </div>
      ) : sortedItems.length === 0 ? (
        <div className="preset-picker-empty" data-testid="preset-picker-empty">
          <p className="preset-picker-empty-msg">{t('presets.empty')}</p>
        </div>
      ) : (
        <ul className="preset-picker-list">
          {sortedItems.map((item) => {
            const isSystem = item.source === 'system';
            return (
              <li
                key={item.slug}
                className={
                  isSystem
                    ? 'preset-picker-item preset-picker-item-system'
                    : 'preset-picker-item'
                }
                data-testid={`preset-item-${item.slug}`}
                data-source={item.source}
              >
                <div className="preset-picker-item-head">
                  <span className="preset-picker-item-name">{item.name}</span>
                  {isSystem && (
                    <span
                      className="preset-picker-system-chip"
                      title={t('presets.systemTooltip')}
                      data-testid={`preset-system-chip-${item.slug}`}
                    >
                      <span className="material-icons" aria-hidden="true">verified</span>
                      {t('presets.systemBadge')}
                    </span>
                  )}
                </div>
                <div className="preset-picker-scopes">
                  {item.categories.map((c) => (
                    <span
                      key={c}
                      className="preset-picker-scope-chip"
                      title={categoryLabel(c, t)}
                    >
                      <span className="material-icons" aria-hidden="true">
                        {categoryIcon(c)}
                      </span>
                      {categoryLabel(c, t)}
                    </span>
                  ))}
                </div>
                <div className="preset-picker-item-actions">
                  <button
                    type="button"
                    className="preset-picker-apply-btn"
                    onClick={() => handleApply(item)}
                    data-testid={`preset-apply-${item.slug}`}
                  >
                    <span className="material-icons" aria-hidden="true">download</span>
                    {t('presets.apply')}
                  </button>
                  {!isSystem && (
                    <button
                      type="button"
                      className="preset-picker-delete-btn"
                      onClick={() => handleDelete(item.slug)}
                      disabled={pendingDelete === item.slug}
                      title={t('presets.delete')}
                      aria-label={`${t('presets.delete')}: ${item.name}`}
                      data-testid={`preset-delete-${item.slug}`}
                    >
                      <span className="material-icons" aria-hidden="true">delete</span>
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
