import { useRef, useEffect, useState, useMemo, CSSProperties } from 'react';
import { useI18n } from '../i18n';

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

const CHAMPIONSHIP_LAYOUT_ID = '446a382f-25c0-4d1d-ae25-48373334e06b';

export interface OverlayPreviewProps {
  overlayUrl: string;
  x: number;
  y: number;
  width: number;
  height: number;
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
  x,
  y,
  width,
  height,
  layoutId,
  cardWidth = 300,
  styleOverride,
}: OverlayPreviewProps) {
  const { t } = useI18n();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [customBounds, setCustomBounds] = useState<Bounds | null>(null);
  // Unique token per mount — forces the browser to bypass cache when the iframe
  // is recreated (e.g. after page reload or navigating back from ConfigPanel),
  // ensuring the overlay page re-establishes its WebSocket connection immediately.
  const [cacheBust] = useState<number>(() => Date.now());

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

  const isUnoOverlay = !!(
    safeOverlayUrl
    && (safeOverlayUrl.hostname === 'overlays.uno'
        || safeOverlayUrl.hostname.endsWith('.overlays.uno'))
  );
  const isCustomOverlay = !!(
    (layoutId && (layoutId.startsWith('C-') || layoutId === 'auto'))
    || (safeOverlayUrl && !isUnoOverlay)
  );

  useEffect(() => {
    if (!isCustomOverlay || !safeOverlayUrl) return;
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
  }, [isCustomOverlay, safeOverlayUrl]);

  if (!safeOverlayUrl) return null;

  if (isCustomOverlay) {
    const cardHeight = cardWidth * 9 / 16;
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
        <div style={wrapperStyle}>
          <iframe
            src={getBustedUrl(
              safeOverlayUrl,
              styleOverride ? { style: styleOverride } : {},
            )}
            width={iframeW}
            height={iframeH}
            style={{ border: 0, background: 'transparent' }}
            sandbox="allow-scripts allow-same-origin"
            allowTransparency
            title={t('preview.title')}
            data-testid="overlay-preview"
          />
        </div>
      </div>
    );
  }

  // --- Standard overlay (overlays.uno) ---
  const championship = layoutId === CHAMPIONSHIP_LAYOUT_ID;
  const iframeWidth = 600;
  const iframeHeight = iframeWidth * 9 / 16;

  // Match the custom-overlay path: render in a 16:9 box so both
  // preview kinds occupy the same visual slot. Previously the UNO
  // path used a card half the height of the overlay's region, which
  // made the scoreboard render in a tiny strip jammed up against the
  // match-point / side-switch pills directly above. Sharing the
  // 16:9 frame with the custom path centers the scoreboard with
  // breathing room above and below.
  const cardHeight = cardWidth * 9 / 16;

  const regionW = (width / 100) * iframeWidth;
  const regionH = (height / (championship ? 60 : 100)) * iframeHeight;

  const leftCoord = x - width / 2;
  const topCoord = y - height * (5 / 17);
  const leftPx = ((leftCoord + 50) / 100) * iframeWidth;
  const topPx = championship
    ? (topCoord / 100) * iframeHeight
    : ((topCoord + 50) / 100) * iframeHeight;

  // ``* 0.95`` mirrors the custom-overlay path so both previews
  // leave the same small inset between the rendered scoreboard and
  // the card edge.
  const scale = regionW > 0 && regionH > 0
    ? Math.min(cardWidth / regionW, cardHeight / regionH) * 0.95
    : 1;

  const src = getBustedUrl(safeOverlayUrl, { aspect: '16:9' });

  return (
    <div
      className="preview-container"
      style={{ width: cardWidth, height: cardHeight, overflow: 'hidden', display: 'flex', justifyContent: 'center', alignItems: 'center' }}
    >
      <div
        style={{
          width: regionW,
          height: regionH * 8 / 10,
          overflow: 'hidden',
          position: 'relative',
          transform: `scale(${scale})`,
          transformOrigin: 'center center',
        }}
      >
        <iframe
          src={src}
          width={iframeWidth}
          height={iframeHeight}
          style={{ border: 0, background: 'transparent', position: 'absolute', top: -topPx, left: -leftPx }}
          sandbox="allow-scripts allow-same-origin"
          allowTransparency={'true' as unknown as boolean}
          title={t('preview.title')}
          data-testid="overlay-preview"
        />
      </div>
    </div>
  );
}
