import { useI18n } from '../../i18n';

export interface ConfigErrorBannerProps {
  message: string;
  onRetry: () => void;
  retryDisabled?: boolean;
  /** Omitted for failures the operator cannot usefully dismiss. */
  onDismiss?: (() => void) | undefined;
  testId: string;
}

/** The config panel's inline failure notice: what went wrong, a retry, and
 *  (where dismissing makes sense) a close button. */
export default function ConfigErrorBanner({
  message,
  onRetry,
  retryDisabled = false,
  onDismiss,
  testId,
}: ConfigErrorBannerProps) {
  const { t } = useI18n();
  return (
    <div className="config-save-error" role="alert" data-testid={testId}>
      <span className="material-icons" aria-hidden="true">
        error_outline
      </span>
      <span className="config-save-error-message">{message}</span>
      <button
        type="button"
        className="config-save-error-retry"
        onClick={onRetry}
        disabled={retryDisabled}
        data-testid={`${testId.replace(/-banner$/, '')}-retry`}
      >
        <span className="material-icons" aria-hidden="true">
          refresh
        </span>
        {t('config.retry')}
      </button>
      {onDismiss && (
        <button
          type="button"
          className="config-save-error-dismiss"
          onClick={onDismiss}
          aria-label={t('config.dismiss')}
          title={t('config.dismiss')}
          data-testid={`${testId.replace(/-banner$/, '')}-dismiss`}
        >
          <span className="material-icons" aria-hidden="true">
            close
          </span>
        </button>
      )}
    </div>
  );
}
