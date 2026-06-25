import { useI18n } from '../../i18n';
import type { ConfigModel } from './TeamsSection';

interface PositionField {
  labelKey: string;
  key: string;
  def: number;
  min: number;
  max: number;
  step: number;
  testId: string;
}

const FIELDS: PositionField[] = [
  {
    labelKey: 'position.height',
    key: 'Height',
    def: 10,
    min: 0,
    max: 100,
    step: 0.1,
    testId: 'height-input',
  },
  {
    labelKey: 'position.width',
    key: 'Width',
    def: 30,
    min: 0,
    max: 100,
    step: 0.1,
    testId: 'width-input',
  },
  {
    labelKey: 'position.hPos',
    key: 'Left-Right',
    def: -33,
    min: -50,
    max: 50,
    step: 0.1,
    testId: 'hpos-input',
  },
  {
    labelKey: 'position.vPos',
    key: 'Up-Down',
    def: -41.1,
    min: -50,
    max: 50,
    step: 0.1,
    testId: 'vpos-input',
  },
  {
    labelKey: 'position.scale',
    key: 'Scale',
    def: 100,
    min: 10,
    max: 300,
    step: 1,
    testId: 'scale-input',
  },
  {
    labelKey: 'position.margin',
    key: 'Margin',
    def: 0,
    min: -25,
    max: 25,
    step: 0.5,
    testId: 'margin-input',
  },
];

// The 3×3 anchor grid. Each cell pins the overlay's matching corner/edge
// to a screen zone; the overlay measures its own rendered size so the
// same zone lands flush for any style (the wide beach board or the tiny
// micro capsule alike). ``free`` falls back to absolute Left-Right /
// Up-Down coordinates (the legacy behaviour).
const ANCHOR_CELLS = [
  { value: 'top-left', v: 'top', h: 'left' },
  { value: 'top-center', v: 'top', h: 'center' },
  { value: 'top-right', v: 'top', h: 'right' },
  { value: 'middle-left', v: 'middle', h: 'left' },
  { value: 'middle-center', v: 'middle', h: 'center' },
  { value: 'middle-right', v: 'middle', h: 'right' },
  { value: 'bottom-left', v: 'bottom', h: 'left' },
  { value: 'bottom-center', v: 'bottom', h: 'center' },
  { value: 'bottom-right', v: 'bottom', h: 'right' },
] as const;

export interface PositionSectionProps {
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
}

export default function PositionSection({ model, updateField }: PositionSectionProps) {
  const { t } = useI18n();

  const rawAnchor = (model as Record<string, unknown>)['Anchor'];
  const anchor =
    typeof rawAnchor === 'string' && rawAnchor.trim() ? rawAnchor.trim().toLowerCase() : 'free';
  const isZone = anchor !== 'free';

  const defOf = (key: string) => FIELDS.find((f) => f.key === key)?.def ?? 0;

  function selectAnchor(value: string) {
    updateField('Anchor', value);
    // Reset the fine nudge so a freshly picked zone lands flush — the
    // legacy absolute defaults (-33 / -41.1) would otherwise read as a
    // large offset once the field switches to nudge semantics.
    updateField('Left-Right', 0);
    updateField('Up-Down', 0);
  }

  function selectFree() {
    updateField('Anchor', 'free');
    // Leaving zone mode: the nudge values (0/0) would be reinterpreted as an
    // absolute coordinate (canvas centre). Restore the absolute defaults so
    // the overlay doesn't jump. Only when actually transitioning out of a
    // zone, so re-clicking "free" never clobbers a custom position.
    if (isZone) {
      updateField('Left-Right', defOf('Left-Right'));
      updateField('Up-Down', defOf('Up-Down'));
    }
  }

  return (
    <div className="config-section-position">
      <div className="config-anchor">
        <div className="config-anchor-head">
          <label className="config-label">{t('position.anchorTitle')}</label>
          <button
            type="button"
            className={`config-anchor-free${!isZone ? ' is-active' : ''}`}
            aria-pressed={!isZone}
            onClick={selectFree}
            data-testid="anchor-free"
          >
            {t('position.anchorFree')}
          </button>
        </div>
        <div className="config-anchor-grid" role="group" aria-label={t('position.anchorTitle')}>
          {ANCHOR_CELLS.map((c) => {
            const active = isZone && anchor === c.value;
            const label = `${t(`position.zone.${c.v}`)} ${t(`position.zone.${c.h}`)}`;
            return (
              <button
                key={c.value}
                type="button"
                className={`config-anchor-cell${active ? ' is-active' : ''}`}
                aria-pressed={active}
                aria-label={label}
                title={label}
                onClick={() => selectAnchor(c.value)}
                data-testid={`anchor-${c.value}`}
              >
                <span className="config-anchor-dot" aria-hidden="true" />
              </button>
            );
          })}
        </div>
        <p className="config-anchor-hint">{t('position.anchorHint')}</p>
      </div>

      <div className="config-stepper-grid">
        {FIELDS.map((f) => {
          const raw = model[f.key];
          const parsed = typeof raw === 'string' ? parseFloat(raw) : raw;
          const val = typeof parsed === 'number' && !Number.isNaN(parsed) ? parsed : f.def;
          // In zone mode the horizontal/vertical fields are a nudge off
          // the anchor rather than an absolute coordinate, so relabel them.
          const labelKey =
            isZone && f.key === 'Left-Right'
              ? 'position.nudgeH'
              : isZone && f.key === 'Up-Down'
                ? 'position.nudgeV'
                : f.labelKey;
          return (
            <div key={f.key} className="config-stepper-group">
              <label className="config-label">{t(labelKey)}</label>
              <div className="config-stepper">
                <button
                  className="config-stepper-btn"
                  onClick={() =>
                    updateField(f.key, Math.max(f.min, parseFloat((val - f.step).toFixed(1))))
                  }
                  title={t('position.decrease')}
                >
                  −
                </button>
                <input
                  type="number"
                  className="config-stepper-input"
                  value={val}
                  min={f.min}
                  max={f.max}
                  step={f.step}
                  onChange={(e) => {
                    // Guard NaN (empty/partial input): writing it would persist
                    // ``null`` for the coordinate (JSON.stringify(NaN) === "null").
                    const n = parseFloat(e.target.value);
                    if (!Number.isNaN(n)) updateField(f.key, n);
                  }}
                  data-testid={f.testId}
                />
                <button
                  className="config-stepper-btn"
                  onClick={() =>
                    updateField(f.key, Math.min(f.max, parseFloat((val + f.step).toFixed(1))))
                  }
                  title={t('position.increase')}
                >
                  +
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
