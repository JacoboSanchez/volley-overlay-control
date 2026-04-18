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
  { labelKey: 'position.height', key: 'Height', def: 10, min: 0, max: 100, step: 0.1, testId: 'height-input' },
  { labelKey: 'position.width', key: 'Width', def: 30, min: 0, max: 100, step: 0.1, testId: 'width-input' },
  { labelKey: 'position.hPos', key: 'Left-Right', def: -33, min: -50, max: 50, step: 0.1, testId: 'hpos-input' },
  { labelKey: 'position.vPos', key: 'Up-Down', def: -41.1, min: -50, max: 50, step: 0.1, testId: 'vpos-input' },
];

export interface PositionSectionProps {
  model: ConfigModel;
  updateField: (key: string, value: unknown) => void;
}

export default function PositionSection({ model, updateField }: PositionSectionProps) {
  const { t } = useI18n();
  return (
    <div className="config-section-position">
      <div className="config-stepper-grid">
        {FIELDS.map((f) => {
          const raw = model[f.key];
          const val = typeof raw === 'number' ? raw : typeof raw === 'string' ? parseFloat(raw) || f.def : f.def;
          return (
            <div key={f.key} className="config-stepper-group">
              <label className="config-label">{t(f.labelKey)}</label>
              <div className="config-stepper">
                <button className="config-stepper-btn"
                  onClick={() => updateField(f.key, Math.max(f.min, parseFloat((val - f.step).toFixed(1))))}
                  title={t('position.decrease')}>−</button>
                <input type="number" className="config-stepper-input"
                  value={val} min={f.min} max={f.max} step={f.step}
                  onChange={(e) => updateField(f.key, parseFloat(e.target.value))}
                  data-testid={f.testId}
                />
                <button className="config-stepper-btn"
                  onClick={() => updateField(f.key, Math.min(f.max, parseFloat((val + f.step).toFixed(1))))}
                  title={t('position.increase')}>+</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
