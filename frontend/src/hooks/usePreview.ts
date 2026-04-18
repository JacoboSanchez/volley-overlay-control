import { useState, useEffect } from 'react';
import * as api from '../api/client';

export interface PreviewData {
  overlayUrl: string;
  x: number;
  y: number;
  width: number;
  height: number;
  layoutId: string;
}

export function usePreview(oid: string | null, showPreview: boolean): PreviewData | null {
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);

  useEffect(() => {
    if (!oid || !showPreview) {
      setPreviewData(null);
      return;
    }
    let cancelled = false;
    setPreviewData(null);
    api.getLinks(oid).then((links) => {
      if (cancelled) return;
      const overlay = typeof links?.overlay === 'string' ? links.overlay : '';
      const preview = typeof links?.preview === 'string' ? links.preview : '';
      if (overlay && preview) {
        const params = new URLSearchParams(preview.split('?')[1] || '');
        setPreviewData({
          overlayUrl: overlay,
          x: parseFloat(params.get('x') ?? '') || 0,
          y: parseFloat(params.get('y') ?? '') || 0,
          width: parseFloat(params.get('width') ?? '') || 30,
          height: parseFloat(params.get('height') ?? '') || 10,
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
