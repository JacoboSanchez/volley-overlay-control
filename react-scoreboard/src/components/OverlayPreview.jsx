import React, { useRef, useEffect, useState } from 'react';

const CHAMPIONSHIP_LAYOUT_ID = '446a382f-25c0-4d1d-ae25-48373334e06b';

/**
 * Renders an overlay preview by loading the full overlay output page in a
 * hidden iframe and using CSS transforms to crop/scale to just the scoreboard
 * region.  Mirrors the logic in app/preview.py create_iframe_card().
 */
export default function OverlayPreview({ overlayUrl, x, y, width, height, layoutId, cardWidth = 300 }) {
  const containerRef = useRef(null);
  const [customBounds, setCustomBounds] = useState(null);

  const isCustomOverlay = layoutId && (layoutId.startsWith('C-') || layoutId === 'auto')
    || (overlayUrl && !overlayUrl.includes('overlays.uno'));

  // Listen for postMessage from custom overlays reporting their render area
  useEffect(() => {
    if (!isCustomOverlay) return;
    function onMessage(event) {
      if (event.data?.type === 'overlayRenderArea') {
        setCustomBounds(event.data.bounds);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [isCustomOverlay]);

  if (!overlayUrl) return null;

  if (isCustomOverlay) {
    const cardHeight = cardWidth * 9 / 16;
    const iframeW = 1920;
    const iframeH = 1080;

    let wrapperStyle = {
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
            src={overlayUrl}
            width={iframeW}
            height={iframeH}
            style={{ border: 0 }}
            title="Overlay preview"
            data-testid="overlay-preview"
          />
        </div>
      </div>
    );
  }

  // --- Standard overlay (overlays.uno) ---
  const championship = layoutId === CHAMPIONSHIP_LAYOUT_ID;
  const iframeWidth = 600;
  const iframeHeight = iframeWidth * 9 / 16; // 337.5

  const cardHeight = cardWidth * height / width;

  // Region size in iframe pixels
  const regionW = (width / 100) * iframeWidth;
  const regionH = (height / (championship ? 60 : 100)) * iframeHeight;

  // Top-left corner in abstract coords → iframe pixels
  const leftCoord = x - width / 2;
  const topCoord = y - height * (5 / 17);
  const leftPx = ((leftCoord + 50) / 100) * iframeWidth;
  const topPx = championship
    ? (topCoord / 100) * iframeHeight
    : ((topCoord + 50) / 100) * iframeHeight;

  // Scale to fit region into the card
  const scale = regionW > 0 && regionH > 0
    ? Math.min(cardWidth / regionW, (cardHeight / 2) / regionH)
    : 1;

  // Append background param like preview.py does
  const separator = overlayUrl.includes('?') ? '&' : '?';
  const src = `${overlayUrl}${separator}bgcolor=rgb(29,29,29)&aspect=16:9`;

  return (
    <div
      className="preview-container"
      style={{ width: cardWidth, height: cardHeight / 2, overflow: 'hidden', display: 'flex', justifyContent: 'center', alignItems: 'center' }}
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
          style={{ border: 0, position: 'absolute', top: -topPx, left: -leftPx }}
          title="Overlay preview"
          data-testid="overlay-preview"
        />
      </div>
    </div>
  );
}
