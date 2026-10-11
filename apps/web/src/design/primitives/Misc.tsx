import * as RT from '@radix-ui/react-tabs';
import * as RTip from '@radix-ui/react-tooltip';
import type { CSSProperties, ReactNode } from 'react';
import s from './Misc.module.css';

/* ------------------------------------------------------------------ Tabs */

interface TabsProps {
  value: string;
  onValueChange: (v: string) => void;
  tabs: { value: string; label: ReactNode; count?: number | null }[];
  children?: ReactNode;
  label: string;
}

export function Tabs({ value, onValueChange, tabs, children, label }: TabsProps) {
  return (
    <RT.Root value={value} onValueChange={onValueChange} className={s.tabsRoot}>
      <RT.List className={s.tabList} aria-label={label}>
        {tabs.map((t) => (
          <RT.Trigger key={t.value} value={t.value} className={s.tab}>
            {t.label}
            {t.count ? <span className={s.count}>{t.count}</span> : null}
          </RT.Trigger>
        ))}
      </RT.List>
      {children}
    </RT.Root>
  );
}

export const TabPanel = ({ value, children }: { value: string; children: ReactNode }) => (
  <RT.Content value={value} className={s.tabPanel}>
    {children}
  </RT.Content>
);

/* ------------------------------------------------------------- Segmented */

interface SegmentedProps<T extends string> {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
  size?: 'sm' | 'md';
}

export function Segmented<T extends string>({ value, onChange, options, label, size = 'sm' }: SegmentedProps<T>) {
  return (
    <div role="radiogroup" aria-label={label} className={[s.segmented, s[`seg-${size}`]].join(' ')}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={s.segment}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            const idx = options.findIndex((x) => x.value === value);
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
              e.preventDefault();
              onChange(options[(idx + 1) % options.length]!.value);
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
              e.preventDefault();
              onChange(options[(idx - 1 + options.length) % options.length]!.value);
            }
          }}
          tabIndex={o.value === value ? 0 : -1}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- Tooltip */

export function TooltipProvider({ children }: { children: ReactNode }) {
  return <RTip.Provider delayDuration={300}>{children}</RTip.Provider>;
}

export function Tooltip({ content, children, side = 'top' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left' }) {
  return (
    <RTip.Root>
      <RTip.Trigger asChild>{children}</RTip.Trigger>
      <RTip.Portal>
        <RTip.Content side={side} sideOffset={6} className={s.tooltip}>
          {content}
        </RTip.Content>
      </RTip.Portal>
    </RTip.Root>
  );
}

/* -------------------------------------------------------------- Skeleton */

export function Skeleton({ width = '100%', height = 14, style, radius = 4 }: { width?: number | string; height?: number; style?: CSSProperties; radius?: number }) {
  return <span className={s.skeleton} style={{ width, height, borderRadius: radius, ...style }} aria-hidden />;
}

export function SkeletonRows({ rows = 5 }: { rows?: number }) {
  return (
    <div className={s.skelRows} role="status" aria-busy="true" aria-label="Yükleniyor">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={s.skelRow}>
          <Skeleton width={18} height={18} radius={4} />
          <div className={s.skelText}>
            <Skeleton width={`${50 + ((i * 17) % 35)}%`} height={14} />
            <Skeleton width={`${30 + ((i * 23) % 40)}%`} height={12} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------ EmptyState */

export function EmptyState({ icon, title, children, actions }: { icon?: ReactNode; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className={s.empty}>
      {icon && <div className={s.emptyIcon}>{icon}</div>}
      <h2 className={s.emptyTitle}>{title}</h2>
      {children && <div className={s.emptyText}>{children}</div>}
      {actions && <div className={s.emptyActions}>{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- List/Row */

export function List({ children, label, density = 'comfortable' }: { children: ReactNode; label: string; density?: 'comfortable' | 'compact' }) {
  return (
    <ul className={[s.list, density === 'compact' ? s.compact : ''].join(' ')} aria-label={label}>
      {children}
    </ul>
  );
}

export function Row({ children, active, className }: { children: ReactNode; active?: boolean; className?: string }) {
  return <li className={[s.row, active ? s.rowActive : '', className].filter(Boolean).join(' ')}>{children}</li>;
}

/* ------------------------------------------------------------------- Kbd */

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className={s.kbd}>{children}</kbd>;
}

/* --------------------------------------------------------------- Section */

export function Section({ title, actions, children, id }: { title: ReactNode; actions?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className={s.section} aria-labelledby={id ? `${id}-h` : undefined} id={id}>
      <div className={s.sectionHead}>
        <h2 id={id ? `${id}-h` : undefined} className={s.sectionTitle}>
          {title}
        </h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
