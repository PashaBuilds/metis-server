import { Segmented } from '@/design/primitives';
import { useSession } from '@/app/session';
import { useTheme, type ThemePref } from '@/app/theme';
import { tr } from '@/i18n/tr';
import s from './Settings.module.css';

export function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  const session = useSession();
  const density = session.pref<'comfortable' | 'compact'>('density', 'comfortable');
  return (
    <div className={s.stack}>
      <section className={s.block} aria-labelledby="theme-h">
        <h2 id="theme-h" className={s.blockTitle}>
          {tr.theme.label}
        </h2>
        <p className={s.hint}>{tr.settings.themeHint}</p>
        <Segmented<ThemePref>
          label={tr.theme.label}
          size="md"
          value={theme}
          onChange={setTheme}
          options={[
            { value: 'system', label: tr.theme.system },
            { value: 'light', label: tr.theme.light },
            { value: 'dark', label: tr.theme.dark },
          ]}
        />
      </section>
      <section className={s.block} aria-labelledby="density-h">
        <h2 id="density-h" className={s.blockTitle}>
          {tr.theme.density}
        </h2>
        <p className={s.hint}>{tr.settings.densityHint}</p>
        <Segmented<'comfortable' | 'compact'>
          label={tr.theme.density}
          size="md"
          value={density}
          onChange={(v) => session.setPref('density', v)}
          options={[
            { value: 'comfortable', label: tr.theme.comfortable },
            { value: 'compact', label: tr.theme.compact },
          ]}
        />
      </section>
    </div>
  );
}
