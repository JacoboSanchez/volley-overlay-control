import { useState, useEffect, useCallback, useMemo } from 'react';
import OverlayPreview from './components/OverlayPreview';
import { I18nProvider, useI18n } from './i18n';

const SCALE_MIN = 0.5;
const SCALE_MAX = 2.0;
const SCALE_STEP = 0.2;

function readNumberParam(params: URLSearchParams, key: string, fallback: number): number {
  const v = params.get(key);
  if (v === null || v === '') return fallback;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : fallback;
}

function PreviewPageInner() {
  const { t } = useI18n();

  const queryParams = useMemo(
    () => new URLSearchParams(window.location.search),
    [],
  );
  const overlayUrl = queryParams.get('output') || '';
  const x = readNumberParam(queryParams, 'x', 0);
  const y = readNumberParam(queryParams, 'y', 0);
  const width = readNumberParam(queryParams, 'width', 100);
  const height = readNumberParam(queryParams, 'height', 100);
  const layoutId = queryParams.get('layout_id') || '';

  const [scale, setScale] = useState<number>(1);
  const [darkBackdrop, setDarkBackdrop] = useState<boolean>(true);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [pageWidth, setPageWidth] = useState<number>(window.innerWidth);

  useEffect(() => {
    const onResize = () => setPageWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  const cardWidth = Math.max(120, Math.round((pageWidth / 1.2) * scale));

  const onZoomIn = useCallback(
    () => setScale((s) => Math.min(SCALE_MAX, +(s + SCALE_STEP).toFixed(2))),
    [],
  );
  const onZoomOut = useCallback(
    () => setScale((s) => Math.max(SCALE_MIN, +(s - SCALE_STEP).toFixed(2))),
    [],
  );
  const onToggleBackdrop = useCallback(() => setDarkBackdrop((v) => !v), []);
  const onToggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  }, []);

  if (!overlayUrl) {
    return <div className="preview-page-empty">{t('preview.missingOutput')}</div>;
  }

  return (
    <div className={`preview-page ${darkBackdrop ? 'preview-page--dark' : 'preview-page--light'}`}>
      <div className="preview-page-stage">
        <OverlayPreview
          overlayUrl={overlayUrl}
          x={x}
          y={y}
          width={width}
          height={height}
          layoutId={layoutId || undefined}
          cardWidth={cardWidth}
        />
      </div>
      <div className="preview-page-toolbar" data-testid="preview-toolbar">
        <button
          type="button"
          className="preview-tool-btn"
          title={t('preview.zoomOut')}
          aria-label={t('preview.zoomOut')}
          onClick={onZoomOut}
          disabled={scale <= SCALE_MIN}
        >
          <span className="material-icons">remove</span>
        </button>
        <button
          type="button"
          className="preview-tool-btn"
          title={t('preview.zoomIn')}
          aria-label={t('preview.zoomIn')}
          onClick={onZoomIn}
          disabled={scale >= SCALE_MAX}
        >
          <span className="material-icons">add</span>
        </button>
        <div className="preview-tool-spacer" />
        <button
          type="button"
          className="preview-tool-btn"
          title={darkBackdrop ? t('ctrl.lightMode') : t('ctrl.darkMode')}
          aria-label={darkBackdrop ? t('ctrl.lightMode') : t('ctrl.darkMode')}
          onClick={onToggleBackdrop}
        >
          <span className="material-icons">{darkBackdrop ? 'light_mode' : 'dark_mode'}</span>
        </button>
        <button
          type="button"
          className="preview-tool-btn"
          title={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
          aria-label={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
          onClick={onToggleFullscreen}
        >
          <span className="material-icons">{isFullscreen ? 'fullscreen_exit' : 'fullscreen'}</span>
        </button>
      </div>
    </div>
  );
}

export default function PreviewApp() {
  return (
    <I18nProvider>
      <PreviewPageInner />
    </I18nProvider>
  );
}
