import ELK, { type ElkExtendedEdge, type ElkNode } from 'elkjs/lib/elk-api';
// ELK ayrı bir worker'da çalışır: 200 düğümlük yerleşim (~2 sn) arayüzü kilitlemez.
import elkWorkerUrl from 'elkjs/lib/elk-worker.min.js?url';

export const NODE_W = 216;
export const NODE_H = 56;
const LABEL_H = 18;

export interface Point {
  x: number;
  y: number;
}

export interface LayoutResult {
  nodes: Map<string, Point>;
  edges: Map<string, { points: Point[]; label: Point | null }>;
  width: number;
  height: number;
}

interface InEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

let elk: InstanceType<typeof ELK> | null = null;
const getElk = () => (elk ??= new ELK({ workerUrl: elkWorkerUrl }));

/** IBM Plex Sans 12 px için kaba genişlik tahmini (ELK etiket alanı ayırsın diye). */
const labelWidth = (text: string) => Math.ceil(text.length * 6.6) + 12;

/**
 * Katmanlı (layered) yerleşim, ortogonal kenar yönlendirme: PCB izleri gibi dik açılı.
 * Etiketler kenarın ortasına yerleşir; ELK etiketler için yer ayırır.
 */
export async function layoutGraph(nodeIds: string[], edges: InEdge[]): Promise<LayoutResult> {
  const graph: ElkNode = {
    id: 'root',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.spacing.nodeNodeBetweenLayers': '88',
      'elk.spacing.nodeNode': '28',
      'elk.layered.spacing.edgeNodeBetweenLayers': '20',
      'elk.spacing.edgeEdge': '12',
      'elk.spacing.edgeLabel': '4',
      'elk.edgeLabels.placement': 'CENTER',
      'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.separateConnectedComponents': 'true',
      'elk.spacing.componentComponent': '48',
      'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
    },
    children: nodeIds.map((id) => ({ id, width: NODE_W, height: NODE_H })),
    edges: edges.map(
      (e): ElkExtendedEdge => ({
        id: e.id,
        sources: [e.source],
        targets: [e.target],
        labels: [{ id: `${e.id}:l`, text: e.label, width: labelWidth(e.label), height: LABEL_H }],
      }),
    ),
  };
  const out = await getElk().layout(graph);
  const nodes = new Map<string, Point>();
  for (const c of out.children ?? []) nodes.set(c.id, { x: c.x ?? 0, y: c.y ?? 0 });
  const res = new Map<string, { points: Point[]; label: Point | null }>();
  for (const e of (out.edges ?? []) as ElkExtendedEdge[]) {
    const sec = e.sections?.[0];
    if (!sec) continue;
    const points = [sec.startPoint, ...(sec.bendPoints ?? []), sec.endPoint].map((p) => ({ x: p.x, y: p.y }));
    const l = e.labels?.[0];
    res.set(e.id, { points, label: l && l.x !== undefined && l.y !== undefined ? { x: l.x + (l.width ?? 0) / 2, y: l.y + (l.height ?? 0) / 2 } : null });
  }
  return { nodes, edges: res, width: out.width ?? 0, height: out.height ?? 0 };
}

/** Ortogonal köşeleri 45° pahlar (PCB izi görünümü). */
export function tracePath(points: Point[], chamfer = 6): string {
  if (points.length < 2) return '';
  const p0 = points[0]!;
  let d = `M${p0.x},${p0.y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i - 1]!;
    const b = points[i]!;
    const c = points[i + 1]!;
    const l1 = Math.hypot(b.x - a.x, b.y - a.y);
    const l2 = Math.hypot(c.x - b.x, c.y - b.y);
    const r = Math.min(chamfer, l1 / 2, l2 / 2);
    if (r < 0.5) {
      d += `L${b.x},${b.y}`;
      continue;
    }
    const p = { x: b.x - ((b.x - a.x) / l1) * r, y: b.y - ((b.y - a.y) / l1) * r };
    const q = { x: b.x + ((c.x - b.x) / l2) * r, y: b.y + ((c.y - b.y) / l2) * r };
    d += `L${p.x},${p.y}L${q.x},${q.y}`;
  }
  const last = points[points.length - 1]!;
  return `${d}L${last.x},${last.y}`;
}
