import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { X } from 'lucide-react';
import s from './Chip.module.css';

interface ChipProps {
  children: ReactNode;
  label?: string;
  onRemove?: () => void;
  onClick?: () => void;
  tone?: 'neutral' | 'muted';
  title?: string;
}

/** Kapsam ve etiket gösterimi. Meta bilgiler " · " zinciri yerine chip ile gösterilir. */
export function Chip({ children, label, onRemove, onClick, tone = 'neutral', title }: ChipProps) {
  const body = (
    <>
      {label && <span className={s.dim}>{label}:</span>}
      <span className={s.value}>{children}</span>
    </>
  );
  return (
    <span className={[s.chip, s[tone]].join(' ')} title={title}>
      {onClick ? (
        <button type="button" className={s.inner} onClick={onClick}>
          {body}
        </button>
      ) : (
        <span className={s.inner}>{body}</span>
      )}
      {onRemove && (
        <button type="button" className={s.remove} onClick={onRemove} aria-label={`Kaldır: ${label ? label + ' ' : ''}${String(children)}`}>
          <X size={14} aria-hidden />
        </button>
      )}
    </span>
  );
}

export function ChipButton({ children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type="button" className={[s.chip, s.neutral, s.add].join(' ')} {...rest}>
      {children}
    </button>
  );
}
