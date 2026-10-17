import { Segmented } from '@/design/primitives';
import { useTheme, type ThemePref } from '@/app/theme';
import { tr } from '@/i18n/tr';
import s from './Settings.module.css';

export function AppearanceTab() {
  const { theme, setTheme } = useTheme();
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
    </div>
  );
}
