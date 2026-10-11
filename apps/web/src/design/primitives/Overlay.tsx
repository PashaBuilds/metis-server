import * as RD from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Button, IconButton } from './Button';
import s from './Overlay.module.css';

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  width?: number;
}

/** Erişilebilir diyalog: focus trap, Esc, başlık/açıklama bağlı. */
export function Dialog({ open, onOpenChange, title, description, children, footer, width = 520 }: DialogProps) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className={s.overlay} />
        <RD.Content className={s.dialog} style={{ maxWidth: width }} aria-describedby={description ? undefined : undefined}>
          <div className={s.head}>
            <RD.Title className={s.title}>{title}</RD.Title>
            <RD.Close asChild>
              <IconButton label="Kapat" size="sm">
                <X size={18} aria-hidden />
              </IconButton>
            </RD.Close>
          </div>
          {description ? <RD.Description className={s.desc}>{description}</RD.Description> : <RD.Description className="sr-only">{title}</RD.Description>}
          {children && <div className={s.body}>{children}</div>}
          {footer && <div className={s.footer}>{footer}</div>}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

interface ConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<void> | void;
}

/** window.confirm yerine: erişilebilir onay diyaloğu. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, danger, onConfirm }: ConfirmProps) {
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Vazgeç
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            loading={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await onConfirm();
                onOpenChange(false);
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}

interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  side?: 'left' | 'right';
  children: ReactNode;
  width?: number;
}

export function Drawer({ open, onOpenChange, title, side = 'right', children, width = 420 }: DrawerProps) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className={s.overlay} />
        <RD.Content className={[s.drawer, s[side]].join(' ')} style={{ width: `min(${width}px, 92vw)` }}>
          <div className={s.head}>
            <RD.Title className={s.title}>{title}</RD.Title>
            <RD.Close asChild>
              <IconButton label="Kapat" size="sm">
                <X size={18} aria-hidden />
              </IconButton>
            </RD.Close>
          </div>
          <RD.Description className="sr-only">{title}</RD.Description>
          <div className={s.drawerBody}>{children}</div>
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}
