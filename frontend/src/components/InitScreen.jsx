import React, { useState, useEffect, useCallback } from 'react';
import { useI18n } from '../i18n';
import * as api from '../api/client';

export default function InitScreen({ oidInput, setOidInput, onSubmit, onSelect, error }) {
  const { t } = useI18n();
  const [predefinedOverlays, setPredefinedOverlays] = useState([]);

  useEffect(() => {
    api.getOverlays().then((data) => {
      let overlays = [];
      if (Array.isArray(data)) {
        overlays = data
          .map((item) => {
            if (item && typeof item === 'object' && item.oid) {
              return { oid: item.oid, name: item.name || item.oid };
            }
            if (typeof item === 'string' && item) {
              return { oid: item, name: item };
            }
            return null;
          })
          .filter(Boolean);
      } else if (data && typeof data === 'object') {
        overlays = Object.entries(data).map(([name, oid]) => ({ oid, name }));
      }
      setPredefinedOverlays(overlays);
    }).catch((err) => {
      console.warn('Failed to fetch predefined overlays:', err);
    });
  }, []);

  const handleOverlaySelect = useCallback((e) => {
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
