import * as DM from '@radix-ui/react-dropdown-menu';
import { MoreHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import s from './shared.module.css';

export interface MenuAction {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
  separatorBefore?: boolean;
}

/** "…" menüsü (Radix): klavye ile gezinilir, Esc kapatır. */
export function RowMenu({ label, actions, trigger }: { label: string; actions: MenuAction[]; trigger?: ReactNode }) {
  return (
    <DM.Root modal={false}>
      <DM.Trigger asChild>
        {trigger ?? (
          <button type="button" className={s.menuTrigger} aria-label={label} title={label}>
            <MoreHorizontal size={18} aria-hidden />
          </button>
        )}
      </DM.Trigger>
      <DM.Portal>
        <DM.Content className={s.menu} align="end" sideOffset={4} collisionPadding={12}>
          {actions.map((a) => (
            <div key={a.label}>
              {a.separatorBefore && <DM.Separator className={s.menuSep} />}
              <DM.Item className={[s.menuItem, a.danger ? s.menuDanger : ''].join(' ')} onSelect={a.onSelect}>
                <span className={s.menuIcon}>{a.icon}</span>
                {a.label}
              </DM.Item>
            </div>
          ))}
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}
