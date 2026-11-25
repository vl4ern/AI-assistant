import { useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  SettingsContext,
  loadSettings,
  makeT,
  type AppSettings,
  type SettingsContextValue,
} from './settings';

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = settings.theme;
    root.dataset.lang = settings.lang;
    root.dataset.font = settings.fontSize;
    try {
      localStorage.setItem('assistant-settings', JSON.stringify(settings));
    } catch {
      // localStorage недоступен — настройки живут до перезагрузки
    }
  }, [settings]);

  const value = useMemo<SettingsContextValue>(
    () => ({
      theme: settings.theme,
      lang: settings.lang,
      fontSize: settings.fontSize,
      locale: settings.lang === 'en' ? 'en-US' : 'ru-RU',
      setTheme: (theme) => setSettings((prev) => ({ ...prev, theme })),
      setLang: (lang) => setSettings((prev) => ({ ...prev, lang })),
      setFontSize: (fontSize) => setSettings((prev) => ({ ...prev, fontSize })),
      t: makeT(settings.lang),
    }),
    [settings]
  );

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}
