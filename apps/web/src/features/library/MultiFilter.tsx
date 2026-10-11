import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';
import { Checkbox } from '@/design/primitives';
import { tr } from '@/i18n/tr';
import s from './Library.module.css';

/** Çoklu seçimli filtre (YATT / Kart / Proje). */
export function MultiFilter({ label, options, value, onChange }: { label: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button type="button" className={[s.filterBtn, value.length ? s.filterOn : ''].join(' ')} aria-label={value.length ? `${label}: ${tr.library.selected(value.length)}` : label}>
          <span>{label}</span>
          {value.length > 0 && <span className={s.filterCount}>{value.length}</span>}
          <ChevronDown size={14} aria-hidden />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className={s.filterPop} sideOffset={6} align="start" collisionPadding={12}>
          <fieldset className={s.filterSet}>
            <legend className="sr-only">{label}</legend>
            {options.length === 0 && <p className={s.filterNone}>{tr.library.noDomainValues}</p>}
            {options.map((o) => (
              <Checkbox
                key={o}
                label={o}
                checked={value.includes(o)}
                onChange={(on) => onChange(on ? [...value, o] : value.filter((x) => x !== o))}
              />
            ))}
          </fieldset>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
