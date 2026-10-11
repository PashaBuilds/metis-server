import { ChevronRight } from 'lucide-react';
import { useId, useLayoutEffect, useRef, useState } from 'react';
import { tr } from '@/i18n/tr';
import { formatMs, formatPercent } from '@/lib/format';
import s from './Lab.module.css';

export interface ChartPoint {
  id: string;
  name: string;
  accuracy: number;
  p50: number;
  critical: number;
  n: number;
}

const M = { top: 16, right: 28, bottom: 44, left: 52 };

/** Yuvarlak eksen adımları: 1 · 2 · 2,5 · 5 × 10^n. */
function niceTicks(max: number): number[] {
  const target = max > 0 ? max : 100;
  const raw = target / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((st) => st >= raw) ?? 10 * mag;
  const n = Math.ceil(target / step);
  return Array.from({ length: n + 1 }, (_, i) => i * step);
}

/**
 * Kalite ve gecikme dağılımı (tek seri: modeller). x = benchmark p50 (ms), y = doğruluk.
 * Kritik hatalı model rengin yanında şekil (✕) ve etiketle ayrılır; renk tek başına sinyal değil.
 * Satır içi SVG; renkler tema tokenlarından (iki temada çalışır). Değerler tablo görünümünde de var.
 */
export function QualityChart({ points }: { points: ChartPoint[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const titleId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const hasPoints = points.length > 0;
  // SVG piksel ölçüsünde çizilir (viewBox ölçeklenmez) — dar ekranda yazılar 12 px altına inmez.
  const [W, setW] = useState(640);
  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(280, Math.round(el.clientWidth))));
    ro.observe(el);
    setW(Math.max(280, Math.round(el.clientWidth)));
    return () => ro.disconnect();
  }, [hasPoints]);
  const H = Math.round(Math.min(320, Math.max(240, W * 0.47)));
  const IW = W - M.left - M.right;
  const IH = H - M.top - M.bottom;
  if (!points.length) return <p className={s.hint}>{tr.lab.chartEmpty}</p>;
  const xTicks = niceTicks(Math.max(...points.map((p) => p.p50)) * 1.1);
  const xMax = xTicks[xTicks.length - 1]!;
  const x = (v: number) => M.left + (v / xMax) * IW;
  const y = (v: number) => M.top + (1 - v) * IH;
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const labelAll = points.length <= 6 && W >= 420;
  const active = points.find((p) => p.id === hover) ?? null;

  return (
    <figure className={s.chart}>
      <div className={s.chartLegend} aria-hidden>
        <span className={s.legendItem}>
          <svg width="14" height="14" viewBox="0 0 14 14">
            <circle cx="7" cy="7" r="5" className={s.dot} />
          </svg>
          {tr.lab.chartOk}
        </span>
        <span className={s.legendItem}>
          <svg width="14" height="14" viewBox="0 0 14 14">
            <path d="M3 3 L11 11 M11 3 L3 11" className={s.cross} />
          </svg>
          {tr.lab.chartCritical}
        </span>
      </div>
      <div className={s.chartBox} ref={boxRef}>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className={s.chartSvg} role="group" aria-labelledby={titleId}>
          <title id={titleId}>{tr.lab.chart}</title>
          {yTicks.map((t) => (
            <g key={`y${t}`}>
              <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className={s.grid} />
              <text x={M.left - 8} y={y(t)} textAnchor="end" dominantBaseline="central" className={s.tick}>
                %{Math.round(t * 100)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <g key={`x${t}`}>
              {t > 0 && <line x1={x(t)} x2={x(t)} y1={M.top} y2={M.top + IH} className={s.grid} />}
              <text x={x(t)} y={M.top + IH + 16} textAnchor="middle" className={s.tick}>
                {Math.round(t)}
              </text>
            </g>
          ))}
          <line x1={M.left} x2={W - M.right} y1={M.top + IH} y2={M.top + IH} className={s.axis} />
          <text x={M.left + IW / 2} y={H - 6} textAnchor="middle" className={s.axisLabel}>
            {tr.lab.chartX}
          </text>
          <text transform={`translate(14 ${M.top + IH / 2}) rotate(-90)`} textAnchor="middle" className={s.axisLabel}>
            {tr.lab.chartY}
          </text>
          {points.map((p) => {
            const px = x(p.p50);
            const py = y(p.accuracy);
            const right = px < W - 170;
            return (
              <g
                key={p.id}
                className={s.point}
                tabIndex={0}
                role="img"
                aria-label={tr.lab.chartPoint(p.name, formatPercent(p.accuracy), formatMs(p.p50), p.critical)}
                onPointerEnter={() => setHover(p.id)}
                onPointerLeave={() => setHover((h) => (h === p.id ? null : h))}
                onFocus={() => setHover(p.id)}
                onBlur={() => setHover((h) => (h === p.id ? null : h))}
              >
                <circle cx={px} cy={py} r={14} className={s.hit} />
                {p.critical ? (
                  <path d={`M${px - 5} ${py - 5} L${px + 5} ${py + 5} M${px + 5} ${py - 5} L${px - 5} ${py + 5}`} className={s.cross} />
                ) : (
                  <circle cx={px} cy={py} r={5} className={s.dot} />
                )}
                {labelAll && (
                  <text x={right ? px + 12 : px - 12} y={py} textAnchor={right ? 'start' : 'end'} dominantBaseline="central" className={s.pointLabel}>
                    {p.critical ? `${p.name} — ${tr.lab.chartCritical}` : p.name}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {active && (
          <div className={s.tooltip} style={{ left: `${(x(active.p50) / W) * 100}%`, top: `${(y(active.accuracy) / H) * 100}%` }} role="presentation">
            <strong className="tabular">{formatPercent(active.accuracy)}</strong>
            <span className="tabular">p50 {formatMs(active.p50)}</span>
            <span>{active.name}</span>
            {active.critical > 0 && <span>{tr.lab.benchCritical(active.critical)}</span>}
          </div>
        )}
      </div>
      <figcaption className={s.hint}>{tr.lab.chartDesc}</figcaption>
      <details className={s.tableToggle}>
        <summary>
          <ChevronRight size={14} aria-hidden className={s.chev} />
          {tr.lab.chartTable}
        </summary>
        <table className={s.miniTable}>
          <thead>
            <tr>
              <th scope="col">{tr.lab.colModel}</th>
              <th scope="col">{tr.lab.chartY}</th>
              <th scope="col">{tr.lab.chartX}</th>
              <th scope="col">{tr.lab.chartCritical}</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="tabular">{formatPercent(p.accuracy)}</td>
                <td className="tabular">{formatMs(p.p50)}</td>
                <td className="tabular">{p.critical}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
