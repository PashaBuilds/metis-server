import { Handle, Position, type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import { memo } from 'react';
import { PageKindIcon } from '@/features/shared/kinds';
import { tracePath, type Point } from './layout';
import s from './Map.module.css';

export type CircuitNodeData = {
  title: string;
  kind: string;
  focus: boolean;
  selected: boolean;
  onPath: boolean;
  dim: boolean;
};
export type CircuitNode = Node<CircuitNodeData, 'circuit'>;

/** Bileşen ayak izi: ince çerçeveli dikdörtgen, kenarlarda pin çizgileri, tür ikonu + başlık. */
export const CircuitNodeView = memo(function CircuitNodeView({ data, id }: NodeProps<CircuitNode>) {
  return (
    <div
      className={[s.node, data.focus ? s.nodeFocus : '', data.selected ? s.nodeSelected : '', data.onPath ? s.nodePath : '', data.dim ? s.nodeDim : ''].join(' ')}
      data-node-id={id}
    >
      <Handle type="target" position={Position.Left} className={s.handle} isConnectable={false} />
      <span className={s.pinsLeft} aria-hidden />
      <span className={s.pinsRight} aria-hidden />
      <PageKindIcon kind={data.kind} size={16} />
      <span className={s.nodeTitle}>{data.title}</span>
      <Handle type="source" position={Position.Right} className={s.handle} isConnectable={false} />
    </div>
  );
});

export type TraceEdgeData = {
  points: Point[];
  label: string;
  labelPos: Point | null;
  highlight: 'path' | 'near' | null;
  dim: boolean;
};
export type TraceEdge = Edge<TraceEdgeData, 'trace'>;

/** Ortogonal mürekkep/gri iz (altın değil — altın kanıta ayrılmış) ve ilişki etiketi. */
export const TraceEdgeView = memo(function TraceEdgeView({ data }: EdgeProps<TraceEdge>) {
  if (!data || data.points.length < 2) return null;
  const d = tracePath(data.points);
  const cls = [s.trace, data.highlight === 'path' ? s.tracePath : data.highlight === 'near' ? s.traceNear : '', data.dim ? s.traceDim : ''].join(' ');
  const end = data.points[data.points.length - 1]!;
  const lw = Math.ceil(data.label.length * 6.6) + 10;
  return (
    <g className={cls}>
      <path d={d} className={s.tracePathLine} fill="none" />
      <circle cx={end.x} cy={end.y} r={2.5} className={s.traceEnd} />
      {data.labelPos && (
        <g transform={`translate(${data.labelPos.x},${data.labelPos.y})`} className={s.traceLabel}>
          <rect x={-lw / 2} y={-9} width={lw} height={18} rx={3} />
          <text textAnchor="middle" dominantBaseline="central">
            {data.label}
          </text>
        </g>
      )}
    </g>
  );
});

export const nodeTypes = { circuit: CircuitNodeView };
export const edgeTypes = { trace: TraceEdgeView };
