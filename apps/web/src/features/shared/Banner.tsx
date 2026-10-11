import { AlertTriangle, Info, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import s from './shared.module.css';

/** Sayfa üstü durum bandı: ne oldu + ne yapılabilir. Her zaman ikon + metin. */
export function Banner({ tone = 'dikkat', children, actions }: { tone?: 'dikkat' | 'celiski' | 'bilgi'; children: ReactNode; actions?: ReactNode }) {
  const Icon = tone === 'celiski' ? XCircle : tone === 'bilgi' ? Info : AlertTriangle;
  return (
    <div className={[s.banner, s[`banner-${tone}`]].join(' ')} role="status">
      <Icon size={18} aria-hidden className={s.bannerIcon} />
      <div className={s.bannerText}>{children}</div>
      {actions && <div className={s.bannerActions}>{actions}</div>}
    </div>
  );
}
