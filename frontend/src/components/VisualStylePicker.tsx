import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../i18n';
import { getScopedItem, setScopedItem, useStorageScope } from '../storage/ScopedStorage';
import { stylePresentation, type StyleKind } from '../styles/catalog';
import { stylePreviewAppearance, type StylePreviewAppearance } from '../styles/preview';
import Dialog from './Dialog';
import OverlayPreview from './OverlayPreview';

interface VisualStylePickerProps {
  kind: StyleKind;
  value: string;
  styles: readonly string[];
  onChange: (style: string) => void;
  disabled?: boolean | undefined;
  testId: string;
  /** Recap examples inherit the configured scoreboard's native/explicit theme. */
  overlayStyle?: string | undefined;
  overlayTheme?: string | undefined;
  /** Recap examples also honour the separate set-summary theme. */
  summaryTheme?: string | undefined;
  configuration?: Record<string, unknown> | undefined;
}

function StyleThumbnail({
  kind,
  id,
  url,
  appearance,
}: {
  kind: StyleKind;
  id: string;
  url: string;
  appearance?: StylePreviewAppearance | undefined;
}) {
  const { t } = useI18n();
  const presentation = stylePresentation(kind, id, t);
  const hostRef = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !appearance || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver(([entry]) => setVisible(!!entry?.isIntersecting));
    observer.observe(host);
    return () => observer.disconnect();
  }, [appearance]);
  return presentation.thumbnail ? (
    <span className="style-thumbnail" ref={hostRef} aria-hidden="true">
      {visible && appearance ? (
        <StyleExample
          url={url}
          summary={kind === 'summary'}
          appearance={appearance}
          thumbnail
          testId={`style-thumbnail-${kind}-${id}`}
        />
      ) : (
        <img src={presentation.thumbnail} alt="" loading="lazy" width={480} height={270} />
      )}
    </span>
  ) : (
    <span className="style-thumbnail-fallback material-icons" aria-hidden="true">
      dashboard
    </span>
  );
}

function StyleExample({
  url,
  summary,
  appearance,
  thumbnail = false,
  testId,
}: {
  url: string;
  summary: boolean;
  appearance?: StylePreviewAppearance | undefined;
  thumbnail?: boolean;
  testId?: string | undefined;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(300);
  useEffect(() => {
    const host = hostRef.current;
    if (!host || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => setWidth(host.clientWidth || 300));
    observer.observe(host);
    return () => observer.disconnect();
  }, []);
  return (
    <div className={`style-example${thumbnail ? ' style-thumbnail-live' : ''}`} ref={hostRef}>
      <OverlayPreview
        overlayUrl={url}
        x={0}
        y={0}
        width={100}
        height={100}
        cardWidth={width}
        fullFrame={summary}
        previewAppearance={appearance}
        testId={testId}
        decorative={thumbnail}
      />
    </div>
  );
}

function readRecent(scope: ReturnType<typeof useStorageScope>, kind: StyleKind): string[] {
  try {
    const stored: unknown = JSON.parse(getScopedItem(scope, `recent-styles-${kind}`) || '[]');
    return Array.isArray(stored)
      ? stored.filter((id): id is string => typeof id === 'string').slice(0, 4)
      : [];
  } catch {
    return [];
  }
}

/** Browsing edits a local candidate; only confirmation calls the mutation handler. */
export default function VisualStylePicker({
  kind,
  value,
  styles,
  onChange,
  disabled,
  testId,
  overlayStyle = 'default',
  overlayTheme = '',
  summaryTheme = '',
  configuration,
}: VisualStylePickerProps) {
  const { t, lang } = useI18n();
  const scope = useStorageScope();
  const appearance = useMemo(
    () => (configuration ? stylePreviewAppearance(configuration, t) : undefined),
    [configuration, t],
  );
  const labelId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [candidate, setCandidate] = useState(value);
  const [category, setCategory] = useState('all');
  const [quick, setQuick] = useState(false);
  const [recent, setRecent] = useState<string[]>([]);
  const current = stylePresentation(kind, value, t);
  const selected = stylePresentation(kind, candidate, t);
  const title = t(kind === 'overlay' ? 'stylePicker.overlayTitle' : 'stylePicker.summaryTitle');
  const categories = [...new Set(styles.map((id) => stylePresentation(kind, id, t).category))];
  const visibleStyles = styles
    .filter((id) => category === 'all' || stylePresentation(kind, id, t).category === category)
    .sort((a, b) => {
      const rank = (id: string) =>
        id === value ? -1 : recent.includes(id) ? recent.indexOf(id) : 10;
      return rank(a) - rank(b);
    });
  const exampleUrl = (id: string) => {
    const params = new URLSearchParams({ lang });
    if (overlayTheme === 'light' || overlayTheme === 'dark') params.set('theme', overlayTheme);
    if (kind === 'summary') {
      params.set('summary', id);
      if (summaryTheme === 'light' || summaryTheme === 'dark')
        params.set('summary_theme', summaryTheme);
    }
    const style = kind === 'summary' ? overlayStyle || 'default' : id;
    return `/overlay-preview/${encodeURIComponent(style)}?${params}`;
  };
  const previewStyle = kind === 'summary' ? overlayStyle || 'default' : candidate;
  const previewUrl = exampleUrl(candidate);
  const canPreview = selected.known && stylePresentation('overlay', previewStyle, t).known;
  const thumbnailAppearance =
    kind === 'summary' && !stylePresentation('overlay', overlayStyle || 'default', t).known
      ? undefined
      : appearance;

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };
  const confirm = () => {
    if (disabled || !styles.includes(candidate)) return;
    if (candidate !== value) onChange(candidate);
    const nextRecent = [candidate, ...recent.filter((id) => id !== candidate)].slice(0, 4);
    try {
      setScopedItem(scope, `recent-styles-${kind}`, JSON.stringify(nextRecent));
    } catch {
      /* Selection also works when browser storage is unavailable. */
    }
    close();
  };

  return (
    <div className="visual-style-picker" data-testid={testId}>
      <button
        type="button"
        className="style-picker-trigger"
        ref={triggerRef}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`${title}: ${current.name}`}
        onClick={() => {
          setCandidate(value);
          setCategory('all');
          setRecent(readRecent(scope, kind));
          setOpen(true);
        }}
      >
        <span className="style-trigger-thumbnail">
          <StyleThumbnail
            kind={kind}
            id={value}
            url={exampleUrl(value)}
            appearance={thumbnailAppearance}
          />
        </span>
        <span className="style-trigger-copy">
          <strong>{current.name}</strong>
          <small>{current.description}</small>
        </span>
        <span className="material-icons" aria-hidden="true">
          expand_more
        </span>
      </button>
      {open &&
        createPortal(
          <div className="style-picker-modal">
            <Dialog open onClose={close} ariaLabelledBy={labelId}>
              <div className="style-gallery-header">
                <h2 id={labelId}>{title}</h2>
                <button
                  type="button"
                  className="style-gallery-close"
                  onClick={close}
                  aria-label={t('dialog.close')}
                >
                  <span className="material-icons" aria-hidden="true">
                    close
                  </span>
                </button>
              </div>
              <div className="style-gallery-body">
                <div className="style-gallery-preview">
                  {canPreview ? (
                    <StyleExample
                      key={previewUrl}
                      url={previewUrl}
                      summary={kind === 'summary'}
                      appearance={appearance}
                    />
                  ) : (
                    <div className="style-example-unavailable">{t('preview.unavailable')}</div>
                  )}
                  <strong>{selected.name}</strong>
                  <p>{selected.description}</p>
                  <small>{t('stylePicker.example')}</small>
                </div>
                <div className="style-gallery-options">
                  <button
                    type="button"
                    className="style-quick-toggle"
                    aria-pressed={quick}
                    onClick={() => setQuick(!quick)}
                  >
                    {t(quick ? 'stylePicker.gallery' : 'stylePicker.quick')}
                  </button>
                  {quick ? (
                    <select
                      className="config-select"
                      aria-label={title}
                      value={candidate}
                      data-testid={`${testId}-quick-select`}
                      disabled={disabled}
                      onChange={(event) => setCandidate(event.target.value)}
                    >
                      {styles.map((id) => (
                        <option key={id} value={id}>
                          {stylePresentation(kind, id, t).name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <>
                      {kind === 'overlay' && (
                        <div className="style-category-filter" aria-label={title}>
                          {['all', ...categories].map((id) => (
                            <button
                              type="button"
                              key={id}
                              aria-pressed={category === id}
                              onClick={() => setCategory(id)}
                            >
                              {t(`stylePicker.${id}`)}
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="style-gallery-grid" role="group" aria-label={title}>
                        {visibleStyles.map((id) => {
                          const item = stylePresentation(kind, id, t);
                          return (
                            <button
                              type="button"
                              key={id}
                              className="style-gallery-option"
                              aria-pressed={candidate === id}
                              disabled={disabled}
                              data-testid={`${kind}-style-${id}`}
                              onClick={() => setCandidate(id)}
                            >
                              <StyleThumbnail
                                kind={kind}
                                id={id}
                                url={exampleUrl(id)}
                                appearance={thumbnailAppearance}
                              />
                              <strong>{item.name}</strong>
                              <small>{item.description}</small>
                              {id === value ? (
                                <span className="style-card-badge">{t('stylePicker.current')}</span>
                              ) : recent.includes(id) ? (
                                <span className="style-card-badge">{t('stylePicker.recent')}</span>
                              ) : null}
                            </button>
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              </div>
              <div className="style-gallery-footer">
                <p>{t(kind === 'overlay' ? 'stylePicker.stagedHint' : 'stylePicker.liveHint')}</p>
                <div>
                  <button type="button" className="dialog-btn" onClick={close}>
                    {t('dialog.cancel')}
                  </button>
                  <button
                    type="button"
                    className="dialog-btn confirm"
                    disabled={disabled || !styles.includes(candidate)}
                    onClick={confirm}
                    data-testid="style-picker-apply"
                  >
                    {t(kind === 'overlay' ? 'stylePicker.select' : 'stylePicker.apply')}
                  </button>
                </div>
              </div>
            </Dialog>
          </div>,
          document.body,
        )}
    </div>
  );
}
