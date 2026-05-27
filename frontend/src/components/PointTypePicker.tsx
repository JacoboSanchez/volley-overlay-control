import { useState } from 'react';
import Dialog from './Dialog';
import { useI18n } from '../i18n';
import { POINT_TYPES, ERROR_TYPES } from '../api/client';
import type { Team, PointType, ErrorType } from '../api/client';

export interface PointTypePickerProps {
  team: Team;
  teamName: string;
  color: string;
  textColor: string;
  /** When true, "opponent error" opens a second step to pick the cause. */
  extendedErrors: boolean;
  /**
   * Commit the point. ``pointType`` omitted ⇒ untyped "quick point";
   * ``errorType`` is only passed alongside ``opp_error``.
   */
  onPick: (pointType?: PointType, errorType?: ErrorType) => void;
  onClose: () => void;
}

/**
 * Opt-in scouting picker shown on a score tap when
 * ``settings.trackPointTypes`` is on. Two steps: the main point-type
 * choices, and (when extended-error tracking is enabled) an
 * opponent-error cause breakdown. "Quick point" scores untyped so the
 * operator can still record a fast point without classifying it.
 */
export default function PointTypePicker({
  teamName,
  color,
  textColor,
  extendedErrors,
  onPick,
  onClose,
}: PointTypePickerProps) {
  const { t } = useI18n();
  const [step, setStep] = useState<'main' | 'error'>('main');
  const titleId = 'point-type-picker-title';

  return (
    <Dialog open onClose={onClose} ariaLabelledBy={titleId}>
      <h3 className="dialog-title" id={titleId}>
        <span
          className="point-picker-team-dot"
          style={{ backgroundColor: color, color: textColor }}
          aria-hidden="true"
        />
        {teamName}
      </h3>

      {step === 'main' ? (
        <>
          <p className="dialog-message">{t('pointPicker.title')}</p>
          <div className="point-picker-grid">
            {POINT_TYPES.map((pt) => (
              <button
                key={pt}
                type="button"
                className="dialog-btn point-picker-btn"
                data-testid={`point-picker-${pt}`}
                onClick={() =>
                  pt === 'opp_error' && extendedErrors ? setStep('error') : onPick(pt)
                }
              >
                {t(`pointType.${pt}`)}
              </button>
            ))}
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="dialog-btn dialog-btn-cancel"
              data-testid="point-picker-quick"
              onClick={() => onPick()}
            >
              {t('pointPicker.quick')}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="dialog-message">{t('errorPicker.title')}</p>
          <div className="point-picker-grid">
            {ERROR_TYPES.map((et) => (
              <button
                key={et}
                type="button"
                className="dialog-btn point-picker-btn"
                data-testid={`point-picker-error-${et}`}
                onClick={() => onPick('opp_error', et)}
              >
                {t(`errorType.${et}`)}
              </button>
            ))}
          </div>
          <div className="dialog-actions">
            <button
              type="button"
              className="dialog-btn"
              data-testid="point-picker-error-generic"
              onClick={() => onPick('opp_error')}
            >
              {t('errorPicker.generic')}
            </button>
            <button
              type="button"
              className="dialog-btn dialog-btn-cancel"
              onClick={() => setStep('main')}
            >
              {t('pointPicker.back')}
            </button>
          </div>
        </>
      )}
    </Dialog>
  );
}
