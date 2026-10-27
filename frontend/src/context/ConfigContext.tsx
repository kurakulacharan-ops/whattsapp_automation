import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getConfig } from '../api/config';
import type { AppConfig } from '../types';

interface ConfigContextValue {
  config: AppConfig | null;
  loading: boolean;
}

const ConfigContext = createContext<ConfigContextValue>({ config: null, loading: true });

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getConfig()
      .then(setConfig)
      .catch(() => {
        // Non-fatal: screens that read config should fall back to sensible
        // display strings ("—" etc.) rather than crash if this call fails.
      })
      .finally(() => setLoading(false));
  }, []);

  return <ConfigContext.Provider value={{ config, loading }}>{children}</ConfigContext.Provider>;
}

export function useConfig() {
  return useContext(ConfigContext);
}
