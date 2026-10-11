import { useEffect } from 'react';
import { useSession } from './session';

export type ThemePref = 'system' | 'light' | 'dark';
const META: Record<'light' | 'dark', string> = { light: '#F3F5F1', dark: '#0E1613' };

export function applyTheme(theme: ThemePref) {
  const root = document.documentElement;
  if (theme === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme);
  try {
    localStorage.setItem('metis.theme', theme);
  } catch {
    /* depolama kapalı olabilir */
  }
  const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', META[dark ? 'dark' : 'light']);
}

/** Sunucudaki kullanıcı tercihini uygular; sistem temasında değişiklikleri izler. */
export function ThemeSync() {
  const { pref, me } = useSession();
  const theme = pref<ThemePref>('theme', 'system');
  const density = pref<'comfortable' | 'compact'>('density', 'comfortable');
  useEffect(() => {
    if (!me) return;
    applyTheme(theme);
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => applyTheme('system');
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme, me]);
  useEffect(() => {
    document.documentElement.dataset.density = density;
  }, [density]);
  return null;
}

export function useTheme() {
  const { pref, setPref } = useSession();
  const theme = pref<ThemePref>('theme', 'system');
  return {
    theme,
    setTheme: (t: ThemePref) => {
      applyTheme(t);
      setPref('theme', t);
    },
    cycle: () => {
      const next: ThemePref = theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system';
      applyTheme(next);
      setPref('theme', next);
    },
  };
}
