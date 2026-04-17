import { useState, useEffect } from 'react';
import * as api from '../api/client';

export function usePreview(oid, showPreview) {
  const [previewData, setPreviewData] = useState(null);

  useEffect(() => {
    if (!oid || !showPreview) {
      setPreviewData(null);
      return;
    }
    let cancelled = false;
    setPreviewData(null); // clear stale data from previous OID
    api.getLinks(oid).then((links) => {
      if (cancelled) return;
      if (links?.overlay && links?.preview) {
        const params = new URLSearchParams(links.preview.split('?')[1] || '');
        setPreviewData({
          overlayUrl: links.overlay,
          x: parseFloat(params.get('x')) || 0,
          y: parseFloat(params.get('y')) || 0,
          width: parseFloat(params.get('width')) || 30,
          height: parseFloat(params.get('height')) || 10,
          layoutId: params.get('layout_id') || '',
        });
      }
    }).catch(() => {
      if (!cancelled) setPreviewData(null);
    });
    return () => { cancelled = true; };
  }, [oid, showPreview]);

  return previewData;
}
