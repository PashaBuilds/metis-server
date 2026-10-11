import { useRef } from 'react';
import { useIz, type IzTarget } from './IzContext';
import s from './Iz.module.css';

interface Props {
  n: number;
  target: IzTarget;
  /** Mentor cevabında sırayla yanma (40 ms aralık) için gecikme (ms). */
  igniteDelay?: number;
}

/** İddia sonundaki altın via işareti: ●n. Enter/tık → İz paneli + iz çizgisi. */
export function ViaMark({ n, target, igniteDelay }: Props) {
  const ref = useRef<HTMLButtonElement>(null);
  const iz = useIz();
  const active = iz.active?.key === target.key;
  return (
    <button
      ref={ref}
      type="button"
      className={[s.via, active ? s.viaActive : '', igniteDelay !== undefined ? s.ignite : ''].join(' ')}
      style={igniteDelay !== undefined ? { animationDelay: `${igniteDelay}ms` } : undefined}
      aria-label={`Kaynak ${n}${target.label ? ': ' + target.label : ''}`}
      aria-expanded={active}
      aria-controls="iz-panel"
      data-iz-marker={target.key}
      onClick={() => (active ? iz.close() : iz.open(target, ref.current))}
    >
      <span className={s.viaDot} data-via-dot aria-hidden />
      <span className={s.viaNum}>{n}</span>
    </button>
  );
}
