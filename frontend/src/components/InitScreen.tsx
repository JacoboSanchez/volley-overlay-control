import { useState, useEffect, useCallback, ChangeEvent, FormEvent } from 'react';
import { useI18n } from '../i18n';
import * as api from '../api/client';

export interface InitScreenProps {
  oidInput: string;
  setOidInput: (value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  onSelect: (oid: string) => void;
  error?: string | null;
}

interface PredefinedOverlay {
  oid: string;
  name: string;
}

function normalizeOverlays(data: unknown): PredefinedOverlay[] {
  if (Array.isArray(data)) {
    return data.flatMap((item): PredefinedOverlay[] => {
      if (item && typeof item === 'object' && 'oid' in item) {
        const entry = item as { oid?: unknown; name?: unknown };
        if (typeof entry.oid === 'string' && entry.oid) {
          const name = typeof entry.name === 'string' && entry.name ? entry.name : entry.oid;
          return [{ oid: entry.oid, name }];
        }
        return [];
      }
      if (typeof item === 'string' && item) return [{ oid: item, name: item }];
      return [];
    });
  }
  if (data && typeof data === 'object') {
    return Object.entries(data as Record<string, unknown>)
      .filter(([, oid]) => typeof oid === 'string')
      .map(([name, oid]) => ({ oid: oid as string, name }));
  }
  return [];
}

export default function InitScreen({ oidInput, setOidInput, onSubmit, onSelect, error }: InitScreenProps) {
  const { t } = useI18n();
  const [predefinedOverlays, setPredefinedOverlays] = useState<PredefinedOverlay[]>([]);

  useEffect(() => {
    api.getOverlays().then((data) => {
      setPredefinedOverlays(normalizeOverlays(data));
    }).catch((err: unknown) => {
      console.warn('Failed to fetch predefined overlays:', err);
    });
  }, []);

  const handleOverlaySelect = useCallback((e: ChangeEvent<HTMLSelectElement>) => {
    setOidInput(e.target.value);
    if (e.target.value) {
      onSelect(e.target.value);
    }
  }, [setOidInput, onSelect]);

  return (
    <div className="init-screen">
      <h1 className="init-title">{t('app.title')}</h1>
      {predefinedOverlays.length > 0 && (
        <div className="init-overlay-selector">
          <label className="init-label">{t('app.selectOverlay')}</label>
          <select
            className="init-select"
            defaultValue=""
            onChange={handleOverlaySelect}
          >
            <option value="">{t('app.selectOverlayPlaceholder')}</option>
            {predefinedOverlays.map((o) => (
              <option key={o.oid} value={o.oid}>{o.name}</option>
            ))}
          </select>
          <div className="init-divider"><span>{t('app.orManualOid')}</span></div>
        </div>
      )}
      <form onSubmit={onSubmit} className="init-form">
        <label className="init-label">{t('app.oidLabel')}</label>
        <input
          className="init-input"
          type="text"
          value={oidInput}
          onChange={(e) => setOidInput(e.target.value)}
          placeholder={t('app.oidPlaceholder')}
          autoFocus={predefinedOverlays.length === 0}
        />
        <button className="init-button" type="submit" disabled={!oidInput.trim()}>
          {t('app.connect')}
        </button>
        {error && <p className="init-error">{error}</p>}
      </form>
    </div>
  );
}
