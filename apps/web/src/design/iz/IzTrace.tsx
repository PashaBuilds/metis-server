import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useIz } from './IzContext';
import s from './Iz.module.css';

interface Geometry {
  d: string;
  start: [number, number];
  end: [number, number];
  length: number;
}

const CHAMFER = 12;

/**
 * İşaretten panele ortogonal, PCB tarzı altın iz: yatay → 45° pah → dikey → 45° pah → yatay.
 * Uçlarda via halkası. Kaydırma/boyut değişiminde yeniden hesaplanır.
 */
/** Ortogonal köşe noktalarını 45° pahlı bir yola çevirir. */
export function chamferPath(points: [number, number][], chamfer = CHAMFER): Geometry {
  const pts = points.filter((p, i) => i === 0 || Math.abs(p[0] - points[i - 1]![0]) + Math.abs(p[1] - points[i - 1]![1]) > 0.5);
  const out: [number, number][] = [pts[0]!];
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1]!;
    const [cx, cy] = pts[i]!;
    const [nx, ny] = pts[i + 1]!;
    const inLen = Math.hypot(cx - px, cy - py);
    const outLen = Math.hypot(nx - cx, ny - cy);
    const c = Math.min(chamfer, inLen / 2, outLen / 2);
    out.push([cx - ((cx - px) / inLen) * c, cy - ((cy - py) / inLen) * c]);
    out.push([cx + ((nx - cx) / outLen) * c, cy + ((ny - cy) / outLen) * c]);
  }
  out.push(pts[pts.length - 1]!);
  let length = 0;
  for (let i = 1; i < out.length; i++) length += Math.hypot(out[i]![0] - out[i - 1]![0], out[i]![1] - out[i - 1]![1]);
  const d = out.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  return { d, start: out[0]!, end: out[out.length - 1]!, length };
}

/**
 * İşaretin altından satır aralığına iner (metnin üzerinden geçmez), aralık boyunca
 * panelin solundaki veri yoluna gider, hedef satıra çıkar/iner ve panele girer.
 */
export function routeTrace(mx: number, markerBottom: number, x2: number, y2: number, gap = 5): Geometry {
  const gapY = markerBottom + gap;
  const bus = Math.max(mx + 24, x2 - 28);
  return chamferPath([
    [mx, markerBottom - 1],
    [mx, gapY],
    [bus, gapY],
    [bus, y2],
    [x2, y2],
  ]);
}

export function IzTrace() {
  const iz = useIz();
  const [geo, setGeo] = useState<Geometry | null>(null);
  const [drawKey, setDrawKey] = useState(0);
  const frame = useRef(0);
  const activeKey = iz.active?.key;

  useLayoutEffect(() => {
    if (!activeKey) {
      setGeo(null);
      return;
    }
    setDrawKey((k) => k + 1);
  }, [activeKey]);

  useEffect(() => {
    if (!activeKey) return;
    const compute = () => {
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => {
        const marker = document.querySelector<HTMLElement>(`[data-iz-marker="${CSS.escape(activeKey)}"]`);
        const panel = document.querySelector<HTMLElement>('[data-iz-panel]');
        if (!marker || !panel) {
          setGeo(null);
          return;
        }
        const m = marker.getBoundingClientRect();
        const p = panel.getBoundingClientRect();
        const target = panel.querySelector<HTMLElement>('[data-iz-target]');
        const body = panel.querySelector<HTMLElement>('[data-iz-panel] pre')?.parentElement;
        let y2 = p.top + 72;
        if (target) {
          const t = target.getBoundingClientRect();
          const b = body?.getBoundingClientRect();
          y2 = t.top + Math.min(t.height, 22) / 2;
          if (b) y2 = Math.min(Math.max(y2, b.top + 10), b.bottom - 10);
        }
        // Panel işaretin solundaysa (dar ekran) çizim yapma.
        if (p.left < m.right + 24 || m.bottom < 0 || m.top > window.innerHeight) {
          setGeo(null);
          return;
        }
        const x2 = body ? body.getBoundingClientRect().left : p.left;
        const dot = marker.querySelector<HTMLElement>('[data-via-dot]')?.getBoundingClientRect() ?? m;
        setGeo(routeTrace(dot.left + dot.width / 2, m.bottom, x2, y2));
      });
    };
    compute();
    const ro = new ResizeObserver(compute);
    ro.observe(document.body);
    window.addEventListener('scroll', compute, true);
    window.addEventListener('resize', compute);
    const mo = new MutationObserver(compute);
    const panel = document.querySelector('[data-iz-panel]');
    if (panel) mo.observe(panel, { childList: true, subtree: true });
    const timer = window.setInterval(compute, 500);
    return () => {
      cancelAnimationFrame(frame.current);
      ro.disconnect();
      mo.disconnect();
      window.clearInterval(timer);
      window.removeEventListener('scroll', compute, true);
      window.removeEventListener('resize', compute);
    };
  }, [activeKey]);

  if (!geo) return null;
  return (
    <svg className={s.traceLayer} aria-hidden data-testid="iz-trace">
      <path
        key={drawKey}
        d={geo.d}
        className={s.tracePath}
        style={{ strokeDasharray: geo.length, ['--trace-len' as string]: `${geo.length}` }}
      />
      <circle cx={geo.start[0]} cy={geo.start[1]} r={3.5} className={s.traceVia} />
      <circle cx={geo.end[0]} cy={geo.end[1]} r={3.5} className={s.traceVia} />
    </svg>
  );
}
