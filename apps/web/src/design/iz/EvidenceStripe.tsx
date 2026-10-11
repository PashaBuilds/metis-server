import type { ReactNode } from 'react';
import { Tooltip } from '../primitives';
import s from './Iz.module.css';

/** Kanıt şeridi: kanıtlı iddia içeren paragrafın solunda 2 px altın çizgi. Kanıtsızda hiçbir şey yok. */
export function EvidenceStripe({ count, children }: { count: number; children: ReactNode }) {
  if (count <= 0) return <div className={s.para}>{children}</div>;
  return (
    <div className={[s.para, s.paraEvidenced].join(' ')}>
      <Tooltip content={`${count} kaynak`} side="left">
        <span className={s.stripe} tabIndex={-1} aria-hidden />
      </Tooltip>
      {children}
    </div>
  );
}
