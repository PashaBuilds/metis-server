import '@xyflow/react/dist/style.css';
import { useQuery } from '@tanstack/react-query';
import { getRouteApi, Link, useNavigate } from '@tanstack/react-router';
import { MiniMap, ReactFlow, ReactFlowProvider, useReactFlow, useStore, type NodeMouseHandler } from '@xyflow/react';
import { ExternalLink, Filter, Focus, Maximize, Network, SlidersHorizontal, ZoomIn, ZoomOut } from 'lucide-react';
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Button, EmptyState, IconButton, Segmented, Select, SkeletonRows } from '@/design/primitives';
import { PageHeader } from '@/app/Shell';
import { ScopeChips } from '@/app/ScopeBar';
import { scopeIsEmpty, useSession } from '@/app/session';
import { tr } from '@/i18n/tr';
import { api, type Schemas } from '@/lib/api/client';
import { useReducedMotion } from '@/lib/hooks';
import { Banner } from '@/features/shared/Banner';
import { messageOf } from '@/features/shared/hooks';
import { FreshnessBadge, PageKindLabel } from '@/features/shared/kinds';
import { asScope } from '@/features/shared/scope';
import { layoutGraph, NODE_H, NODE_W, type LayoutResult } from './layout';
import { edgeTypes, nodeTypes, type CircuitNode, type TraceEdge } from './MapParts';
import s from './Map.module.css';

const route = getRouteApi('/app/harita');
type MapNode = Schemas['MapNode'];
type MapEdge = Schemas['MapEdge'];
type View = 'graph' | 'list';
type Depth = '1' | '2' | '3';
const PREDICATES = Object.keys(tr.relations);

const relLabel = (p: string) => tr.relations[p] ?? p;

function bfs(start: string, adj: Map<string, Set<string>>, depth: number): Set<string> {
  const keep = new Set([start]);
  let frontier = [start];
  for (let d = 0; d < depth; d++) {
    const next: string[] = [];
    for (const n of frontier) for (const nb of adj.get(n) ?? []) {
        if (keep.has(nb)) continue;
        keep.add(nb);
        next.push(nb);
      }
    frontier = next;
  }
  return keep;
}

function shortestPath(a: string, b: string, adj: Map<string, Set<string>>): string[] {
  if (a === b) return [a];
  const prev = new Map<string, string>([[a, a]]);
  const queue = [a];
  while (queue.length) {
    const n = queue.shift()!;
    for (const nb of adj.get(n) ?? []) {
      if (prev.has(nb)) continue;
      prev.set(nb, n);
      if (nb === b) {
        const path = [b];
        let cur = b;
        while (cur !== a) path.push((cur = prev.get(cur)!));
        return path.reverse();
      }
      queue.push(nb);
    }
  }
  return [];
}

export default function MapPage() {
  const session = useSession();
  const pid = session.projectId;
  const search = route.useSearch();
  const navigate = useNavigate({ from: '/harita' });
  const view: View = search.view === 'list' ? 'list' : 'graph';
  // Liste görünümü (erişilebilir alternatif) açıkça bir odak seçilmedikçe tüm ilişkileri gösterir.
  const all = search.all === '1' || (view === 'list' && !search.focus);
  const depth: Depth = search.depth === '1' || search.depth === '3' ? search.depth : '2';
  const predicate = search.predicate && PREDICATES.includes(search.predicate) ? search.predicate : undefined;
  const [moreOpen, setMoreOpen] = useState(!!predicate || depth !== '2');
  const scope = session.scope;
  const predId = useId();

  const map = useQuery({
    queryKey: ['map', pid, predicate ?? null, scope],
    queryFn: () => api.get<Schemas['MapOut']>(`/projects/${pid}/map`, { predicate, domain: scope.domain, yatt: scope.yatt, kart: scope.kart, proje: scope.proje }),
    enabled: !!pid,
    staleTime: 30_000,
  });
  const nodes = useMemo(() => map.data?.nodes ?? [], [map.data]);
  const edges = useMemo(() => map.data?.edges ?? [], [map.data]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const adj = useMemo(() => {
    const m = new Map<string, Set<string>>(nodes.map((n) => [n.id, new Set<string>()]));
    for (const e of edges) {
      m.get(e.source)?.add(e.target);
      m.get(e.target)?.add(e.source);
    }
    return m;
  }, [nodes, edges]);

  // Odak: URL'deki, yoksa en çok bağlantılı bilgi (sunucu dereceye göre sıralar).
  const focusId = search.focus && byId.has(search.focus) ? search.focus : (nodes[0]?.id ?? null);
  const visibleIds = useMemo(() => (all || !focusId ? new Set(nodes.map((n) => n.id)) : bfs(focusId, adj, Number(depth))), [all, focusId, nodes, adj, depth]);
  const visibleNodes = useMemo(() => nodes.filter((n) => visibleIds.has(n.id)), [nodes, visibleIds]);
  const visibleEdges = useMemo(() => edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)), [edges, visibleIds]);

  const [selected, setSelected] = useState<string | null>(null);
  const [path, setPath] = useState<string[]>([]);
  const selectedId = selected && visibleIds.has(selected) ? selected : focusId;

  const setSearch = (patch: Record<string, string | undefined>) => navigate({ search: (old) => ({ ...old, ...patch }), replace: true });

  const recenter = useCallback(
    (id: string) => {
      if (focusId && focusId !== id) setPath(shortestPath(focusId, id, adj));
      setSelected(id);
      navigate({ search: (old) => ({ ...old, focus: id }), replace: true });
    },
    [focusId, adj, navigate],
  );
  const openPage = useCallback((id: string) => navigate({ to: '/bilgi/$pageId', params: { pageId: id }, search: {} }), [navigate]);

  const sel = selectedId ? byId.get(selectedId) : undefined;
  const selEdges = sel ? visibleEdges.filter((e) => e.source === sel.id || e.target === sel.id) : [];

  const moreCount = (predicate ? 1 : 0) + (depth !== '2' ? 1 : 0);
  return (
    <div className={s.page}>
      <PageHeader title={tr.map.title}>
        <div className={s.toolbar}>
          <Segmented<View>
            label={tr.map.viewToggle}
            value={view}
            onChange={(v) => setSearch({ view: v === 'list' ? 'list' : undefined })}
            options={[
              { value: 'graph', label: tr.map.viewGraph },
              { value: 'list', label: tr.map.viewList },
            ]}
          />
          <Button size="sm" variant="secondary" icon={<Filter size={15} aria-hidden />} aria-expanded={moreOpen} onClick={() => setMoreOpen((o) => !o)}>
            {moreCount ? tr.library.moreFiltersN(moreCount) : tr.library.moreFilters}
          </Button>
          {moreOpen && (
          <>
          <span className={s.control}>
            <label htmlFor={predId} className={s.controlLabel}>
              {tr.map.predicate}
            </label>
            <Select id={predId} value={predicate ?? ''} onChange={(e) => setSearch({ predicate: e.target.value || undefined })}>
              <option value="">{tr.map.allPredicates}</option>
              {PREDICATES.map((p) => (
                <option key={p} value={p}>
                  {relLabel(p)}
                </option>
              ))}
            </Select>
          </span>
          <span className={s.control}>
            <span className={s.controlLabel}>{tr.map.depth}</span>
            <Segmented<Depth>
              label={tr.map.depth}
              value={depth}
              onChange={(d) => setSearch({ depth: d === '2' ? undefined : d, all: undefined })}
              options={(['1', '2', '3'] as const).map((d) => ({ value: d, label: tr.map.depthN(Number(d)) }))}
            />
          </span>
          </>
          )}
          <Button size="sm" variant={all ? 'primary' : 'secondary'} aria-pressed={all} icon={<Network size={15} aria-hidden />} onClick={() => setSearch({ all: all ? undefined : '1' })}>
            {tr.map.showAll}
          </Button>
          <span className={s.control}>
            <span className={s.controlLabel}>{tr.map.scope}</span>
            {scopeIsEmpty(scope) ? <span className={s.scopeAll}>{tr.scope.all}</span> : <ScopeChips scope={scope} />}
            <IconButton label={tr.mentor.changeScope} size="sm" onClick={() => window.dispatchEvent(new CustomEvent('metis:open-scope'))}>
              <SlidersHorizontal size={15} aria-hidden />
            </IconButton>
          </span>
          {map.data && (
            <span className={s.count} aria-live="polite">
              {tr.map.nodesShown(visibleNodes.length, map.data.total_nodes)}
            </span>
          )}
        </div>
      </PageHeader>

      {map.isLoading ? (
        <SkeletonRows rows={6} />
      ) : map.isError ? (
        <EmptyState title={tr.shared.loadError} actions={<Button onClick={() => map.refetch()}>{tr.common.retry}</Button>}>
          {messageOf(map.error)}
        </EmptyState>
      ) : nodes.length === 0 ? (
        <EmptyState icon={<Network size={24} />} title={tr.map.emptyTitle}>
          {tr.map.empty}
        </EmptyState>
      ) : (
        <>
          {map.data?.truncated && <Banner tone="dikkat">{tr.map.truncated}</Banner>}
          {view === 'list' ? (
            <ListView nodes={visibleNodes} edges={visibleEdges} byId={byId} />
          ) : (
            <div className={s.graphLayout}>
              <ReactFlowProvider>
                <GraphView
                  nodes={visibleNodes}
                  edges={visibleEdges}
                  focusId={all ? null : focusId}
                  selectedId={selectedId}
                  path={path}
                  showAll={all}
                  onSelect={setSelected}
                  onRecenter={recenter}
                  onOpen={openPage}
                />
              </ReactFlowProvider>
              <aside className={s.side} aria-label={tr.map.selected}>
                {sel ? (
                  <>
                    <PageKindLabel kind={sel.kind} />
                    <h2 className={s.sideTitle}>{sel.title}</h2>
                    <FreshnessBadge freshness={sel.freshness} size="sm" />
                    <p className={s.sideSummary}>{sel.summary || tr.map.noSummary}</p>
                    <ScopeChips scope={asScope(sel.scope)} />
                    <div className={s.sideActions}>
                      <Link to="/bilgi/$pageId" params={{ pageId: sel.id }} search={{}} className={s.primaryLink}>
                        <ExternalLink size={15} aria-hidden />
                        {tr.map.openPage}
                      </Link>
                      {sel.id !== focusId && (
                        <Button size="sm" icon={<Focus size={15} aria-hidden />} onClick={() => recenter(sel.id)}>
                          {tr.map.focusHere}
                        </Button>
                      )}
                    </div>
                    <h3 className={s.sideSub}>{tr.map.neighbors(selEdges.length)}</h3>
                    <ul className={s.neighbors}>
                      {selEdges.map((e) => {
                        const other = byId.get(e.source === sel.id ? e.target : e.source);
                        if (!other) return null;
                        const out = e.source === sel.id;
                        return (
                          <li key={e.id}>
                            <span className={s.nbRel}>{out ? relLabel(e.predicate) : (tr.relationsIn[e.predicate] ?? e.predicate)}</span>
                            <button type="button" className={s.nbLink} onClick={() => recenter(other.id)}>
                              {other.title}
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </>
                ) : null}
              </aside>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface GraphProps {
  nodes: MapNode[];
  edges: MapEdge[];
  focusId: string | null;
  selectedId: string | null;
  path: string[];
  showAll: boolean;
  onSelect: (id: string) => void;
  onRecenter: (id: string) => void;
  onOpen: (id: string) => void;
}

function GraphView({ nodes, edges, focusId, selectedId, path, showAll, onSelect, onRecenter, onOpen }: GraphProps) {
  const rf = useReactFlow();
  const reduced = useReducedMotion();
  const helpId = useId();
  const [layout, setLayout] = useState<LayoutResult | null>(null);
  // Uzak görünümde başlıklar okunmaz: düğümler dolu blok olur, etiketler gizlenir (okunurluk + akıcılık).
  const far = useStore((st) => st.transform[2] < 0.38);
  const [announce, setAnnounce] = useState('');
  const layoutKey = useMemo(() => nodes.map((n) => n.id).join(',') + '|' + edges.map((e) => e.id).join(','), [nodes, edges]);
  const latest = useRef({ nodes, edges });
  latest.current = { nodes, edges };

  useEffect(() => {
    let alive = true;
    const { nodes: ns, edges: es } = latest.current;
    void layoutGraph(
      ns.map((n) => n.id),
      es.map((e) => ({ id: e.id, source: e.source, target: e.target, label: relLabel(e.predicate) })),
    ).then((res) => {
      if (alive) setLayout(res);
    });
    return () => {
      alive = false;
    };
  }, [layoutKey]);

  const pathSet = useMemo(() => new Set(path), [path]);
  const pathEdges = useMemo(() => {
    const out = new Set<string>();
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i]!;
      const b = path[i + 1]!;
      for (const e of edges) if ((e.source === a && e.target === b) || (e.source === b && e.target === a)) out.add(e.id);
    }
    return out;
  }, [path, edges]);

  const rfNodes = useMemo<CircuitNode[]>(() => {
    if (!layout) return [];
    return nodes.map((n) => ({
      id: n.id,
      type: 'circuit',
      position: layout.nodes.get(n.id) ?? { x: 0, y: 0 },
      width: NODE_W,
      height: NODE_H,
      data: { title: n.title, kind: n.kind, focus: n.id === focusId, selected: n.id === selectedId, onPath: pathSet.has(n.id), dim: false },
    }));
  }, [layout, nodes, focusId, selectedId, pathSet]);

  const rfEdges = useMemo<TraceEdge[]>(() => {
    if (!layout) return [];
    return edges.map((e) => {
      const l = layout.edges.get(e.id);
      const near = e.source === selectedId || e.target === selectedId;
      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: 'trace',
        data: { points: l?.points ?? [], label: relLabel(e.predicate), labelPos: l?.label ?? null, highlight: pathEdges.has(e.id) ? 'path' : near ? 'near' : null, dim: false },
      };
    });
  }, [layout, edges, selectedId, pathEdges]);

  // Yeni yerleşimde: odak varsa ona, yoksa tüm haritaya sığdır.
  useEffect(() => {
    if (!layout) return;
    const duration = reduced ? 0 : 300;
    const id = window.requestAnimationFrame(() => {
      const p = focusId ? layout.nodes.get(focusId) : undefined;
      if (p && !showAll && nodes.length > 12) void rf.setCenter(p.x + NODE_W / 2, p.y + NODE_H / 2, { zoom: 0.9, duration });
      else void rf.fitView({ padding: 0.12, duration, maxZoom: 1.1 });
    });
    return () => window.cancelAnimationFrame(id);
    // Yalnız yerleşim değişince.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  const neighborsOf = useCallback(
    (id: string) => {
      const out: string[] = [];
      for (const e of edges) {
        if (e.source === id) out.push(e.target);
        else if (e.target === id) out.push(e.source);
      }
      return [...new Set(out)];
    },
    [edges],
  );

  function move(key: string) {
    if (!layout || !selectedId) return;
    const here = layout.nodes.get(selectedId);
    const nbs = neighborsOf(selectedId);
    if (!here || !nbs.length) return;
    const dir = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[key] as [number, number];
    let best: string | null = null;
    let bestScore = Infinity;
    for (const nb of nbs) {
      const p = layout.nodes.get(nb);
      if (!p) continue;
      const dx = p.x - here.x;
      const dy = p.y - here.y;
      const along = dx * dir[0] + dy * dir[1];
      if (along <= 0) continue;
      const across = Math.abs(dx * dir[1]) + Math.abs(dy * dir[0]);
      const score = along + across * 2;
      if (score < bestScore) {
        bestScore = score;
        best = nb;
      }
    }
    if (!best) {
      // Bu yönde komşu yoksa komşular arasında sırayla dolaş.
      const order = [...nbs].sort();
      const i = order.indexOf(selectedId);
      best = key === 'ArrowRight' || key === 'ArrowDown' ? order[(i + 1) % order.length]! : order[(i - 1 + order.length) % order.length]!;
    }
    onSelect(best);
    const p = layout.nodes.get(best)!;
    const n = nodes.find((x) => x.id === best);
    setAnnounce(tr.map.announce(n?.title ?? '', neighborsOf(best).length));
    void rf.setCenter(p.x + NODE_W / 2, p.y + NODE_H / 2, { zoom: rf.getZoom(), duration: reduced ? 0 : 200 });
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.target !== e.currentTarget) return;
    if (e.key.startsWith('Arrow')) {
      e.preventDefault();
      move(e.key);
    } else if (e.key === 'Enter' && selectedId) {
      e.preventDefault();
      onOpen(selectedId);
    } else if (e.key === ' ' && selectedId) {
      e.preventDefault();
      onRecenter(selectedId);
    } else if (e.key === '+' || e.key === '=') void rf.zoomIn();
    else if (e.key === '-') void rf.zoomOut();
  }

  const onNodeClick: NodeMouseHandler<CircuitNode> = (_e, node) => onRecenter(node.id);

  return (
    <div className={s.canvasWrap}>
      <div
        className={[s.canvas, far ? s.far : ''].join(' ')}
        tabIndex={0}
        role="application"
        aria-label={tr.map.graphLabel}
        aria-describedby={helpId}
        onKeyDown={onKeyDown}
        data-testid="concept-map"
      >
        {!layout && <p className={s.layoutWorking}>{tr.map.layoutWorking}</p>}
        <ReactFlow<CircuitNode, TraceEdge>
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          elementsSelectable={false}
          disableKeyboardA11y
          onNodeClick={onNodeClick}
          onNodeDoubleClick={(_e, node) => onOpen(node.id)}
          minZoom={0.08}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          ariaLabelConfig={tr.map.aria}
          zoomOnDoubleClick={false}
        >
          <MiniMap
            pannable
            zoomable
            ariaLabel={tr.map.minimap}
            className={s.minimap}
            nodeColor={(n) => ((n.data as { focus?: boolean }).focus ? 'var(--murekkep)' : 'var(--cizgi-guclu)')}
            nodeStrokeWidth={0}
            maskColor="color-mix(in srgb, var(--zemin) 70%, transparent)"
          />
        </ReactFlow>
        <div className={s.zoom}>
          <IconButton label={tr.map.zoomIn} size="sm" variant="secondary" onClick={() => void rf.zoomIn({ duration: reduced ? 0 : 150 })}>
            <ZoomIn size={16} aria-hidden />
          </IconButton>
          <IconButton label={tr.map.zoomOut} size="sm" variant="secondary" onClick={() => void rf.zoomOut({ duration: reduced ? 0 : 150 })}>
            <ZoomOut size={16} aria-hidden />
          </IconButton>
          <IconButton label={tr.map.fit} size="sm" variant="secondary" onClick={() => void rf.fitView({ padding: 0.12, duration: reduced ? 0 : 200 })}>
            <Maximize size={16} aria-hidden />
          </IconButton>
        </div>
      </div>
      <p id={helpId} className={s.help}>
        {tr.map.keyboardHelp}
      </p>
      <p className="sr-only" aria-live="polite">
        {announce}
      </p>
    </div>
  );
}

function ListView({ nodes, edges, byId }: { nodes: MapNode[]; edges: MapEdge[]; byId: Map<string, MapNode> }) {
  const rows = [...edges].sort((a, b) => (byId.get(a.source)?.title ?? '').localeCompare(byId.get(b.source)?.title ?? '', 'tr') || a.predicate.localeCompare(b.predicate));
  const linked = new Set(edges.flatMap((e) => [e.source, e.target]));
  const isolated = nodes.filter((n) => !linked.has(n.id));
  const pageLink = (id: string) => {
    const n = byId.get(id);
    return n ? (
      <Link to="/bilgi/$pageId" params={{ pageId: id }} search={{}} className={s.tableLink}>
        {n.title}
      </Link>
    ) : null;
  };
  return (
    <div className={s.listWrap}>
      <table className={s.table}>
        <caption className={s.caption}>{tr.map.listCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{tr.map.colSubject}</th>
            <th scope="col">{tr.map.colRelation}</th>
            <th scope="col">{tr.map.colTarget}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td>{pageLink(e.source)}</td>
              <td>{relLabel(e.predicate)}</td>
              <td>{pageLink(e.target)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {isolated.length > 0 && (
        <section className={s.isolated} aria-labelledby="map-isolated">
          <h2 id="map-isolated" className={s.sideSub}>
            {tr.map.isolated}
          </h2>
          <ul className={s.isoList}>
            {isolated.map((n) => (
              <li key={n.id}>{pageLink(n.id)}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
