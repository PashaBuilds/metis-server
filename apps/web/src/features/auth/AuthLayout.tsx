import type { ReactNode } from 'react';
import { Logo } from '@/design/iz';
import { tr } from '@/i18n/tr';
import s from './Auth.module.css';

/** Giriş/kurulum: solda logo + slogan (uygulamada sloganın tek yeri), sağda form. */
export function AuthLayout({ children, title }: { children: ReactNode; title: string }) {
  return (
    <div className={s.layout}>
      <section className={s.brandSide} aria-label="METIS">
        <div className={s.brandInner}>
          <Logo size={56} tone="rail" />
          <p className={s.wordmark}>METIS</p>
          <p className={s.slogan}>{tr.product.slogan}</p>
        </div>
        <svg className={s.motif} viewBox="0 0 400 300" aria-hidden preserveAspectRatio="xMidYMid slice">
          <path d="M-10 230 H120 L150 200 V120 L180 90 H420" />
          <path d="M-10 260 H200 L230 230 V170 L260 140 H420" className={s.motifFaint} />
          <circle cx="150" cy="200" r="4" />
          <circle cx="180" cy="90" r="4" />
          <circle cx="230" cy="230" r="4" className={s.motifFaint} />
        </svg>
      </section>
      <main className={s.formSide}>
        <div className={s.formInner}>
          <h1 className={s.title}>{title}</h1>
          {children}
        </div>
      </main>
    </div>
  );
}
