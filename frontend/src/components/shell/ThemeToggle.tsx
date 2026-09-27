import { useLocale } from '../../features/local/locale';
import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';
const themeKey = 'ariadne:theme';

function initialTheme(): Theme {
  if (typeof document === 'undefined') return 'light';
  const applied = document.documentElement.dataset.theme;
  if (applied === 'light' || applied === 'dark') return applied;
  try {
    const saved = window.localStorage.getItem(themeKey);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // The system preference remains usable when storage is unavailable.
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { t } = useLocale();
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [feedback, setFeedback] = useState<{ id: number; message: string } | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    if (!feedback) return;
    const timeout = window.setTimeout(() => setFeedback(null), 2400);
    return () => window.clearTimeout(timeout);
  }, [feedback]);

  function toggle() {
    const next = theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    setTheme(next);
    setFeedback((current) => ({ id: (current?.id ?? 0) + 1, message: next === 'dark' ? 'Dark mode is on' : 'Light mode is on' }));
    try {
      window.localStorage.setItem(themeKey, next);
    } catch {
      // The current page still changes theme without persistent storage.
    }
  }

  return <>
    <button className={`theme-toggle${compact ? ' theme-toggle--compact' : ''}`} type="button" aria-label={t('Dark mode')} aria-pressed={theme === 'dark'} onClick={toggle}>
      {compact ? <><span className="theme-toggle__choice" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg></span><span className="theme-toggle__choice" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z"/></svg></span></> : <>
      <span className="theme-toggle__icon" aria-hidden="true">{theme === 'dark' ? '☾' : '☼'}</span>
      <span className="theme-toggle__track" aria-hidden="true"><span className="theme-toggle__thumb"/></span>
      <span>{t('Dark mode')}</span>
      </>}
    </button>
    {feedback && <span className="theme-feedback" role="status" key={feedback.id}><span className="theme-feedback__dot" aria-hidden="true"/>{t(feedback.message)}</span>}
  </>;
}
