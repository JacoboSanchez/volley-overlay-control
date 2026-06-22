import { useRef, useEffect, useState, useMemo, useCallback, CSSProperties } from 'react';
import { useI18n } from '../i18n';

// Fallback timeout for the preview iframe. If we haven't received a single
// ``load`` event within this window the network is almost certainly blocking
// the request (DNS, CSP, firewall) — surface a retryable placeholder so the
// operator isn't staring at a blank rectangle.
const PREVIEW_LOAD_TIMEOUT_MS = 6000;

// Allow only http(s) iframe sources. Rejects javascript:, data:, file:, and
// similar schemes that would let a malicious overlayUrl execute script or
// navigate the iframe off-origin when rendered. Returns the parsed URL on
// success or null on any failure (malformed, wrong scheme, non-string).
function validateHttpUrl(candidate: unknown): URL | null {
  if (typeof candidate !== 'string' || candidate === '') return null;
  try {
    const url = new URL(candidate, window.location.href);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url;
  } catch {
    return null;
  }
}

export interface OverlayPreviewProps {
  overlayUrl: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** Accepted for caller compatibility; the in-process overlay reports its own
   *  render bounds via postMessage, so geometry props are not used to crop. */
  layoutId?: string;
  cardWidth?: number;
  styleOverride?: string;
}

interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Renders an overlay preview by loading the full overlay output page in a
 * hidden iframe and using CSS transforms to crop/scale to just the scoreboard
 * region. Mirrors the logic in app/preview.py create_iframe_card().
 */
export default function OverlayPreview({
  overlayUrl,
  cardWidth = 300,
  styleOverride,
}: OverlayPreviewProps) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [customBounds, setCustomBounds] = useState<Bounds | null>(null);
  // Unique token per mount — forces the browser to bypass cache when the iframe
  // is recreated (e.g. after page reload or navigating back from ConfigPanel),
  // ensuring the overlay page re-establishes its WebSocket connection immediately.
  const [cacheBust, setCacheBust] = useState<number>(() => Date.now());
  // Tracks whether the iframe ever fired ``load`` (or the custom-overlay
  // path posted bounds) so we can show a retryable placeholder when the
  // network silently blocks the request.
  const [loadFailed, setLoadFailed] = useState(false);
  const [iframeLoaded, setIframeLoaded] = useState(false);

  const handleIframeLoad = useCallback(() => {
    setIframeLoaded(true);
    setLoadFailed(false);
  }, []);

  const handleIframeError = useCallback(() => {
    setLoadFailed(true);
  }, []);

  const handleRetry = useCallback(() => {
    setLoadFailed(false);
    setIframeLoaded(false);
    setCustomBounds(null);
    setCacheBust(Date.now());
  }, []);

  useEffect(() => {
    setIframeLoaded(false);
    setLoadFailed(false);
  }, [overlayUrl, cacheBust]);

  useEffect(() => {
    if (iframeLoaded || loadFailed) return undefined;
    const timer = setTimeout(() => {
      // Custom overlays signal readiness via postMessage instead of
      // ``load``; only the standard (cross-origin) iframe needs the
      // timeout fallback.
      if (!iframeLoaded) setLoadFailed(true);
    }, PREVIEW_LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [iframeLoaded, loadFailed, cacheBust]);

  // Parse + scheme-check once; every iframe src downstream derives from this
  // validated URL, so an untrusted overlayUrl (javascript:, data:, …) can
  // never reach the iframe.
  const safeOverlayUrl = useMemo(() => validateHttpUrl(overlayUrl), [overlayUrl]);

  const getBustedUrl = (url: URL, params: Record<string, string> = {}): string => {
    const busted = new URL(url.toString());
    Object.entries(params).forEach(([k, v]) => busted.searchParams.set(k, v));
    busted.searchParams.set('_t', String(cacheBust));
    return busted.toString();
  };

  useEffect(() => {
    if (!safeOverlayUrl) return;
    const allowedOrigin = safeOverlayUrl.origin;
    function onMessage(event: MessageEvent) {
      if (event.origin !== allowedOrigin) return;
      const data = event.data as { type?: string; bounds?: Bounds } | undefined;
      if (data?.type === 'overlayRenderArea' && data.bounds) {
        setCustomBounds(data.bounds);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [safeOverlayUrl]);

  // Memoize the custom-overlay iframe element so it stays referentially
  // stable across re-renders (e.g. when ``customBounds`` updates after the
  // overlay posts new render bounds). Without this, every re-render produces
  // a fresh <iframe> element and React tears down and recreates the DOM node
  // — which reloads the embedded overlay (a visible flash on every side
  // swap, since a swap re-renders this component). Keyed only on inputs that
  // genuinely change the iframe.
  const customIframe = useMemo(() => {
    if (!safeOverlayUrl) return null;
    const src = getBustedUrl(safeOverlayUrl, styleOverride ? { style: styleOverride } : {});
    return (
      <iframe
        src={src}
        width={1920}
        height={1080}
        style={{ border: 0, background: 'transparent' }}
        sandbox="allow-scripts allow-same-origin"
        // Match the standard-overlay iframe below: ``allowTransparency`` is a
        // non-standard attribute React types as boolean, but Chromium honours
        // the string ``"true"`` more reliably, so pass it as that.
        allowTransparency={'true' as unknown as boolean}
        title={t('preview.title')}
        onLoad={handleIframeLoad}
        onError={handleIframeError}
        data-testid="overlay-preview"
      />
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [safeOverlayUrl, styleOverride, cacheBust, t, handleIframeLoad, handleIframeError]);

  if (!safeOverlayUrl) return null;

  // 16:9 card geometry so the scoreboard isn't squeezed into a tiny strip
  // jammed up against the match-point / side-switch pills above.
  const cardHeight = (cardWidth * 9) / 16;

  const fallbackOverlay = loadFailed ? (
    <div
      className="preview-fallback"
      role="status"
      aria-live="polite"
      data-testid="overlay-preview-fallback"
    >
      <span className="material-icons" aria-hidden="true">
        cloud_off
      </span>
      <span className="preview-fallback-message">{t('preview.unavailable')}</span>
      <button type="button" className="preview-fallback-retry" onClick={handleRetry}>
        {t('preview.retry')}
      </button>
    </div>
  ) : null;

  const iframeW = 1920;
  const iframeH = 1080;

  let wrapperStyle: CSSProperties = {
    position: 'absolute',
    width: iframeW,
    height: iframeH,
    transformOrigin: 'top left',
    transform: 'scale(0.12)',
    top: 0,
    left: 0,
    opacity: customBounds ? 1 : 0,
    transition: 'opacity 0.3s ease',
  };

  if (customBounds && customBounds.width > 0 && customBounds.height > 0) {
    const scaleX = cardWidth / customBounds.width;
    const scaleY = cardHeight / customBounds.height;
    const scale = Math.min(scaleX, scaleY) * 0.95;
    const scaledW = customBounds.width * scale;
    const scaledH = customBounds.height * scale;
    const offsetX = (cardWidth - scaledW) / 2 - customBounds.x * scale;
    const offsetY = (cardHeight - scaledH) / 2 - customBounds.y * scale;

    wrapperStyle = {
      ...wrapperStyle,
      transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
      opacity: 1,
    };
  }

  return (
    <div
      ref={containerRef}
      className="preview-container"
      style={{ width: cardWidth, height: cardHeight, position: 'relative' }}
    >
      <div style={wrapperStyle}>{customIframe}</div>
      {fallbackOverlay}
    </div>
  );
}
