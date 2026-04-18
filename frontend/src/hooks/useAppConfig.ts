import { useEffect, useState } from 'react';
import * as api from '../api/client';
import type { AppConfig } from '../api/client';

const DEFAULT_TITLE = 'Volley Scoreboard';

/**
 * Fetch runtime app configuration from the backend on mount and set
 * ``document.title`` to the configured app title. The returned ``title``
 * lets callers render the same value in the UI without a flash of the
 * default while the request is in flight.
 */
export function useAppConfig(): AppConfig {
  const [config, setConfig] = useState<AppConfig>({ title: DEFAULT_TITLE });

  useEffect(() => {
    let cancelled = false;
    api.getAppConfig().then((cfg) => {
      if (cancelled) return;
      setConfig(cfg);
      if (cfg.title) document.title = cfg.title;
    }).catch((err: unknown) => {
      console.warn('Failed to fetch app config:', err);
    });
    return () => { cancelled = true; };
  }, []);

  return config;
}
