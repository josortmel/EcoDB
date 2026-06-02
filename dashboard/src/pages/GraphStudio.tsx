import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import ForceGraph2D from 'react-force-graph-2d';
import { GlassCard } from '../components/GlassCard';
import { asArray } from '../lib/asArray';
import { apiGet } from '../lib/api';
import { errMsg } from '../lib/errMsg';
import { useThemeStore } from '../stores/theme';
import { useToastStore } from '../stores/toast';
import { useAuthMe } from '../hooks/auth';
import { useGraphSubgraph, useGraphAll } from '../hooks/graph';
import { useMergeEntities } from '../hooks/ontology';
import { colorFor, FALLBACK, nodeRadius, endId, linkKey, TAU, type GNode, type GLink, type NodeId, type FgHandle } from '../components/graph/graphTypes';
import { drawNode } from '../components/graph/drawNode';
import { GraphContextMenu } from '../components/graph/ContextMenu';
import { MergeConfirmModal } from '../components/graph/MergeConfirmModal';
import { TunePanel, type TuneValues } from '../components/graph/TunePanel';
import type { SubgraphResponse } from '../types/api';

const ACCENT = 'var(--sec-graph)'; // §2.9 graph #4E9E6A
const DEFAULT_CENTER = 'EcoDB';

function Inspector({ node, relations, onClose }: { node: GNode; relations: { predicate: string; other: string }[]; onClose: () => void }) {
  const { t } = useTranslation();
  const color = node.hot ? 'var(--node-hot)' : colorFor(node.type);
  const Cell = ({ k, v }: { k: string; v: string }) => (
    <div className="rounded-md p-2.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
      <div className="truncate font-mono text-[12.5px] text-ink-1">{v}</div>
      <div className="mt-0.5 font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-3">{k}</div>
    </div>
  );
  return (
    // GlassCard's base class is `relative`; wrap it so OUR absolute positioning wins.
    <div className="pointer-events-auto absolute right-4 top-4 bottom-4 w-[300px]">
      <GlassCard className="flex h-full flex-col p-[18px]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color }}>
              <span className="h-[7px] w-[7px] flex-none rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}` }} />
              {node.type || t('gph.untyped')}
            </div>
            <div className="mt-2 break-words text-[16px] font-semibold leading-tight text-ink-1">{node.name}</div>
          </div>
          <button type="button" onClick={onClose} aria-label={t('gph.inspector.close')} className="grid h-[28px] w-[28px] flex-none place-items-center rounded-md text-ink-2 transition-colors hover:text-ink-1" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} width={14} height={14}><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" /></svg>
          </button>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-2.5">
          <Cell k={t('gph.inspector.typeLabel')} v={node.type || t('gph.untyped')} />
          <Cell k={t('gph.inspector.degree')} v={String(node.degree)} />
          <Cell k={t('gph.inspector.id')} v={String(node.id)} />
        </div>

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{t('gph.inspector.relations')}</div>
          {relations.length === 0 ? (
            <div className="font-mono text-[11.5px] text-ink-3">{t('gph.inspector.noRelations')}</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {relations.map((rel, i) => (
                <div key={`${rel.predicate}-${rel.other}-${i}`} className="flex items-center gap-2 rounded-md px-2.5 py-1.5" style={{ background: 'var(--inset)', boxShadow: 'inset 0 0 0 1px var(--card-hairline)' }}>
                  <span className="flex-none rounded-sm px-1.5 py-0.5 font-mono text-[9.5px] text-ink-2" style={{ background: 'var(--card-bg)' }}>{rel.predicate}</span>
                  <span className="truncate text-[11.5px] text-ink-1">{rel.other}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </GlassCard>
    </div>
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return <div className="absolute inset-0 grid place-items-center font-mono text-[12.5px]" style={{ color: 'var(--screen-text)' }}>{children}</div>;
}

export function GraphStudio() {
  const { t } = useTranslation();
  const theme = useThemeStore((s) => s.theme);
  const toast = useToastStore((s) => s.show);
  const me = useAuthMe();
  const isAdmin = Boolean(me.data?.is_super || me.data?.is_ceo);
  const merge = useMergeEntities();
  const [center, setCenter] = useState(DEFAULT_CENTER);
  const [depth, setDepth] = useState(2);
  const [full, setFull] = useState(false); // whole-graph mode (GET /graph/all)
  const [selected, setSelected] = useState<GNode | null>(null);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<NodeId>>(new Set());
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: GNode | null } | null>(null);
  const [selectionBox, setSelectionBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const [mergeConfirm, setMergeConfirm] = useState<{ source: GNode; target: GNode } | null>(null);
  const [extra, setExtra] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const [expanding, setExpanding] = useState(false);
  const [shiftHeld, setShiftHeld] = useState(false);
  const [tuneOpen, setTuneOpen] = useState(false);
  const [tune, setTune] = useState<TuneValues>({ charge: -60, linkDist: 40, nodeSize: 1, labelZoom: 1.6 });
  const [frozen, setFrozen] = useState(false);
  const [, setPinTick] = useState(0); // bump to repaint after pin
  const fittedRef = useRef(false);
  const FULL_LIMIT = 2000; // > the current 1414 node_count, with headroom; node_count is the real total
  const subQ = useGraphSubgraph(center, depth, !full);
  const allQ = useGraphAll(FULL_LIMIT, full);
  const q = full ? allQ : subQ;

  const palette = useMemo(() => {
    const cs = getComputedStyle(document.documentElement);
    const read = (n: string, f: string) => cs.getPropertyValue(n).trim() || f;
    return {
      edge: read('--edge', 'rgba(150,160,176,0.14)'),
      nodeHot: read('--node-hot', '#ff7a3c'),
      text: read('--screen-text', 'rgba(240,236,228,0.85)'),
    };
  }, [theme]);

  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<FgHandle | undefined>(undefined);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  // Track Shift so the box-select overlay can intercept pointer events (when held)
  // and let the canvas pan/click/drag normally otherwise.
  useEffect(() => {
    const down = (e: KeyboardEvent) => e.key === 'Shift' && setShiftHeld(true);
    const up = (e: KeyboardEvent) => e.key === 'Shift' && setShiftHeld(false);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  // Escape dismisses the open context-menu / merge confirm (BC-1) / tune panel (BH3).
  useEffect(() => {
    if (!contextMenu && !mergeConfirm && !tuneOpen) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setContextMenu(null);
        setMergeConfirm(null);
        setTuneOpen(false);
      }
    };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [contextMenu, mergeConfirm, tuneOpen]);

  // Base subgraph → fresh GNode/GLink objects (cloned so react-force-graph's
  // in-place mutation never touches the query cache).
  const baseData = useMemo(() => {
    const nodes: GNode[] = asArray<GNode>(q.data?.nodes).map((n) => ({ id: n.id, name: n.name, type: n.type, degree: n.degree, hot: n.name === center }));
    const links: GLink[] = asArray<GLink>(q.data?.edges).map((e) => ({ source: endId(e.source), target: endId(e.target), predicate: e.predicate }));
    return { nodes, links };
  }, [q.data, center]);

  // Merge the expanded 1-hop neighbors into the base, deduped by node id and by
  // source-target-predicate. Same object refs are reused → ForceGraph keeps the
  // existing nodes' positions.
  const data = useMemo(() => {
    if (extra.nodes.length === 0 && extra.links.length === 0) return baseData;
    const nodeMap = new Map<NodeId, GNode>();
    for (const n of baseData.nodes) nodeMap.set(n.id, n);
    for (const n of extra.nodes) if (!nodeMap.has(n.id)) nodeMap.set(n.id, n);
    const seen = new Set(baseData.links.map(linkKey));
    const links = [...baseData.links];
    for (const l of extra.links) {
      const k = linkKey(l);
      if (!seen.has(k)) {
        links.push(l);
        seen.add(k);
      }
    }
    return { nodes: [...nodeMap.values()], links };
  }, [baseData, extra]);

  // Apply the tune-panel forces (repel + link distance) and reheat. Re-applied on
  // dataset change since ForceGraph rebuilds its forces for new graphData.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force('charge')?.strength?.(tune.charge);
    fg.d3Force('link')?.distance?.(tune.linkDist);
    fg.d3ReheatSimulation();
  }, [tune.charge, tune.linkDist, data]);

  // Truncation differs by mode: subgraph reports `truncated`; /graph/all is capped
  // when node_count exceeds the page (with FULL_LIMIT 2000 vs 1414, it won't be).
  const truncated = full ? (allQ.data ? allQ.data.node_count > allQ.data.nodes.length : false) : subQ.data?.truncated;
  const shownCount = full ? allQ.data?.nodes.length ?? data.nodes.length : subQ.data?.shown_nodes ?? data.nodes.length;
  const totalCount: number | string = full ? allQ.data?.node_count ?? '—' : subQ.data?.total_nodes ?? '—';
  const selId = selected?.id;

  // Memoized per-node paint (AU-1) — only re-created when the reactive draw inputs
  // change, so ForceGraph isn't handed a fresh callback every render.
  const nodeCanvasObject = useCallback(
    (n: object, ctx: CanvasRenderingContext2D, globalScale: number) => drawNode(n as GNode, ctx, globalScale, { palette, selectedIds, selId, nodeSize: tune.nodeSize, labelZoom: tune.labelZoom }),
    [palette, selectedIds, selId, tune.nodeSize, tune.labelZoom],
  );

  // Hit-canvas paint (IC-1) — memoized like nodeCanvasObject so ForceGraph isn't
  // handed a fresh callback each frame; only the radius input (nodeSize) matters.
  const nodePointerAreaPaint = useCallback(
    (n: object, color: string, ctx: CanvasRenderingContext2D) => {
      const node = n as GNode;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, nodeRadius(node.degree) * tune.nodeSize + 3, 0, TAU);
      ctx.fill();
    },
    [tune.nodeSize],
  );

  // Real relations for the selected node, read off the subgraph edges.
  const relations = useMemo(() => {
    if (!selected) return [];
    const nameById = new Map(data.nodes.map((n) => [n.id, n.name]));
    const out: { predicate: string; other: string }[] = [];
    for (const l of data.links) {
      const s = endId(l.source);
      const tg = endId(l.target);
      if (s === selected.id) out.push({ predicate: l.predicate, other: nameById.get(tg) ?? String(tg) });
      else if (tg === selected.id) out.push({ predicate: l.predicate, other: nameById.get(s) ?? String(s) });
      if (out.length >= 60) break;
    }
    return out;
  }, [selected, data]);

  // Re-fit + reset all interaction state when the dataset (center/depth/full) changes.
  const autoSelectedFor = useRef<string | null>(null);
  useEffect(() => {
    fittedRef.current = false;
    setFrozen(false);
    autoSelectedFor.current = null;
    setSelectedIds(new Set());
    setExtra({ nodes: [], links: [] });
    setContextMenu(null);
    setMergeConfirm(null);
  }, [center, depth, full]);

  // The inspector follows the focal (center) node on load.
  useEffect(() => {
    if (data.nodes.length && autoSelectedFor.current !== center) {
      const c = data.nodes.find((n) => n.name === center);
      if (c) {
        setSelected(c);
        autoSelectedFor.current = center;
      }
    }
  }, [data, center]);

  const recenter = (node: GNode) => {
    setSelected(node);
    setFull(false); // clicking a node leaves whole-graph mode → its centered neighborhood
    if (node.name && node.name !== center) setCenter(node.name);
  };

  const toggleSelect = (id: NodeId) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const expandNeighbors = async (node: GNode) => {
    if (expanding) return; // guard the in-flight request (IC-1)
    setContextMenu(null);
    setExpanding(true);
    try {
      const sub = await apiGet<SubgraphResponse>(`/graph/subgraph?center=${encodeURIComponent(node.name)}&depth=1`);
      const newNodes: GNode[] = asArray<GNode>(sub.nodes).map((n) => ({ id: n.id, name: n.name, type: n.type, degree: n.degree }));
      const newLinks: GLink[] = asArray<GLink>(sub.edges).map((e) => ({ source: endId(e.source), target: endId(e.target), predicate: e.predicate }));
      // dedup against the base + the already-expanded set so `extra` can't grow N×k.
      setExtra((prev) => {
        const haveNodes = new Set([...baseData.nodes, ...prev.nodes].map((n) => n.id));
        const haveLinks = new Set([...baseData.links, ...prev.links].map(linkKey));
        const addNodes = newNodes.filter((n) => !haveNodes.has(n.id));
        const addLinks = newLinks.filter((l) => !haveLinks.has(linkKey(l)));
        if (addNodes.length === 0 && addLinks.length === 0) return prev;
        return { nodes: [...prev.nodes, ...addNodes], links: [...prev.links, ...addLinks] };
      });
      setFrozen(false);
    } catch (e) {
      toast(errMsg(e, t, t('gph.expandFailed')));
    } finally {
      setExpanding(false);
    }
  };

  const doMerge = (keepAlias: boolean) => {
    if (!mergeConfirm) return;
    merge.mutate(
      { source_node_id: Number(mergeConfirm.source.id), target_node_id: Number(mergeConfirm.target.id), keep_as_alias: keepAlias },
      {
        onSuccess: () => {
          toast(t('gph.merge.done', { source: mergeConfirm.source.name, target: mergeConfirm.target.name }));
          setMergeConfirm(null);
          setSelectedIds(new Set());
        },
        onError: (e) => {
          toast(errMsg(e, t, t('gph.merge.failed')));
          setMergeConfirm(null);
        },
      },
    );
  };

  // ── Box-select overlay (active only while Shift is held) ──
  const boxStart = useRef<{ x: number; y: number } | null>(null);
  const localPoint = (e: ReactPointerEvent) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    return { x: e.clientX - (rect?.left ?? 0), y: e.clientY - (rect?.top ?? 0) };
  };
  const onBoxDown = (e: ReactPointerEvent) => {
    if (e.button !== 0) return;
    const p = localPoint(e);
    boxStart.current = p;
    setSelectionBox({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onBoxMove = (e: ReactPointerEvent) => {
    if (!boxStart.current) return;
    const p = localPoint(e);
    setSelectionBox({ x0: boxStart.current.x, y0: boxStart.current.y, x1: p.x, y1: p.y });
  };
  const onBoxUp = (e: ReactPointerEvent) => {
    if (!boxStart.current) return;
    const start = boxStart.current;
    const end = localPoint(e);
    boxStart.current = null;
    setSelectionBox(null);
    const fg = fgRef.current;
    if (!fg) return;
    const dx = Math.abs(end.x - start.x);
    const dy = Math.abs(end.y - start.y);
    if (dx < 4 && dy < 4) {
      // a Shift-click → toggle the nearest node under the cursor
      let hit: GNode | null = null;
      let best = Infinity;
      for (const n of data.nodes) {
        if (n.x == null || n.y == null) continue;
        const sc = fg.graph2ScreenCoords(n.x, n.y);
        const d = Math.hypot(sc.x - end.x, sc.y - end.y);
        const reach = Math.max(8, nodeRadius(n.degree) + 4);
        if (d <= reach && d < best) {
          best = d;
          hit = n;
        }
      }
      if (hit) toggleSelect(hit.id);
      return;
    }
    // a Shift-drag → add every node inside the box to the selection
    const minX = Math.min(start.x, end.x);
    const maxX = Math.max(start.x, end.x);
    const minY = Math.min(start.y, end.y);
    const maxY = Math.max(start.y, end.y);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const n of data.nodes) {
        if (n.x == null || n.y == null) continue;
        const sc = fg.graph2ScreenCoords(n.x, n.y);
        if (sc.x >= minX && sc.x <= maxX && sc.y >= minY && sc.y <= maxY) next.add(n.id);
      }
      return next;
    });
  };

  // DEV-only handles so the Playwright pass can drive the DOM overlays (the real
  // canvas pointer interaction isn't headless-verifiable — that's Pepe's manual check).
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const w = window as unknown as { __graph?: unknown };
    w.__graph = {
      nodeCount: () => data.nodes.length,
      ids: () => data.nodes.map((n) => n.id),
      toggleSelect: (id: NodeId) => toggleSelect(id),
      selectedCount: () => selectedIds.size,
      clearSelection: () => setSelectedIds(new Set()),
      selectVisible: () => setSelectedIds(new Set(data.nodes.map((n) => n.id))),
      openNodeMenu: (id: NodeId) => {
        const n = data.nodes.find((x) => x.id === id);
        if (n) setContextMenu({ x: 160, y: 120, node: n });
      },
      openBgMenu: () => setContextMenu({ x: 160, y: 120, node: null }),
      expand: (id: NodeId) => {
        const n = data.nodes.find((x) => x.id === id);
        if (n) void expandNeighbors(n);
      },
    };
    return () => {
      delete (window as unknown as { __graph?: unknown }).__graph;
    };
    // no deps — intentional: re-expose the latest closures every render so the
    // DEV test hook always reflects current state (stripped from prod by Vite).
  });

  // Legend caps at 12 rows: top 11 + "+N more".
  const typeLegend = useMemo(() => {
    const c = new Map<string, number>();
    for (const n of data.nodes) c.set(n.type || '∅', (c.get(n.type || '∅') ?? 0) + 1);
    const sorted = [...c.entries()].sort((a, b) => b[1] - a[1]);
    if (sorted.length <= 12) return { rows: sorted, more: 0 };
    return { rows: sorted.slice(0, 11), more: sorted.length - 11 };
  }, [data.nodes]);

  // Context-menu action availability.
  const otherSelected = contextMenu?.node ? [...selectedIds].filter((id) => id !== contextMenu.node!.id) : [];
  const mergeTarget = otherSelected.length === 1 ? data.nodes.find((n) => n.id === otherSelected[0]) ?? null : null;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 mt-1.5 flex items-end justify-between gap-4 px-0.5">
        <div>
          <h1 className="font-mono text-[19px] font-medium tracking-[0.01em] text-ink-1">{t('gph.title')}</h1>
          <p className="mt-1.5 text-[12.5px] text-ink-3">{t('gph.subtitle')}</p>
        </div>
      </div>

      <div
        ref={wrapRef}
        onContextMenu={(e) => e.preventDefault()} // suppress the native menu over the graph
        className="relative min-h-0 flex-1 overflow-hidden rounded-lg"
        style={{ background: 'var(--screen-bg)', boxShadow: 'inset 0 2px 22px rgba(0,0,0,0.5), inset 0 0 0 1px rgba(0,0,0,0.45)' }}
      >
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundImage: 'linear-gradient(var(--screen-grid) 1px, transparent 1px), linear-gradient(90deg, var(--screen-grid) 1px, transparent 1px)', backgroundSize: '32px 32px' }}
        />

        {size.w > 0 && data.nodes.length > 0 && (
          <ForceGraph2D
            ref={fgRef as never}
            width={size.w}
            height={size.h}
            graphData={data}
            backgroundColor="rgba(0,0,0,0)"
            cooldownTime={15000}
            enablePanInteraction={!shiftHeld}
            onEngineStop={() => {
              if (!fittedRef.current) {
                fgRef.current?.zoomToFit(400, 60);
                fittedRef.current = true;
              }
              setFrozen(true);
            }}
            onNodeDrag={() => setFrozen(false)}
            onNodeDragEnd={(n: object) => {
              const node = n as GNode;
              node.fx = node.x;
              node.fy = node.y;
              setPinTick((p) => p + 1);
            }}
            onNodeRightClick={(n: object, ev: MouseEvent) => {
              ev.preventDefault();
              const rect = wrapRef.current?.getBoundingClientRect();
              setContextMenu({ x: ev.clientX - (rect?.left ?? 0), y: ev.clientY - (rect?.top ?? 0), node: n as GNode });
            }}
            onBackgroundRightClick={(ev: MouseEvent) => {
              ev.preventDefault();
              const rect = wrapRef.current?.getBoundingClientRect();
              setContextMenu({ x: ev.clientX - (rect?.left ?? 0), y: ev.clientY - (rect?.top ?? 0), node: null });
            }}
            onNodeClick={(n: object, ev: MouseEvent) => {
              if (ev?.shiftKey) toggleSelect((n as GNode).id);
              else recenter(n as GNode);
            }}
            onBackgroundClick={() => {
              setSelected(null);
              setContextMenu(null);
            }}
            linkColor={() => palette.edge}
            linkWidth={() => 0.6}
            nodePointerAreaPaint={nodePointerAreaPaint}
            nodeCanvasObject={nodeCanvasObject}
          />
        )}

        {/* Box-select overlay — captures pointer events only while Shift is held. */}
        <div
          className="absolute inset-0"
          style={{ pointerEvents: shiftHeld ? 'auto' : 'none', cursor: shiftHeld ? 'crosshair' : 'default' }}
          onPointerDown={onBoxDown}
          onPointerMove={onBoxMove}
          onPointerUp={onBoxUp}
          data-testid="gph-boxlayer"
        >
          {selectionBox && (
            <div
              className="absolute"
              style={{
                left: Math.min(selectionBox.x0, selectionBox.x1),
                top: Math.min(selectionBox.y0, selectionBox.y1),
                width: Math.abs(selectionBox.x1 - selectionBox.x0),
                height: Math.abs(selectionBox.y1 - selectionBox.y0),
                background: 'color-mix(in srgb, var(--sec-graph) 12%, transparent)',
                boxShadow: 'inset 0 0 0 1px var(--sec-graph)',
              }}
            />
          )}
        </div>

        {/* truncated banner */}
        {truncated && (
          <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded-md px-3 py-1.5 font-mono text-[10px]" style={{ background: 'color-mix(in srgb, var(--kind-agent) 18%, transparent)', color: 'var(--kind-agent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--kind-agent) 70%, transparent)' }}>
            {t('gph.truncated', { shown: shownCount, total: totalCount })}
          </div>
        )}

        {/* loading / empty / error */}
        {q.isPending && <Overlay>{t('gph.loading')}</Overlay>}
        {q.isError && (
          <Overlay>
            <div className="flex flex-col items-center gap-2">
              <span className="h-[7px] w-[7px] rounded-full" style={{ background: 'var(--red)', boxShadow: '0 0 6px rgba(222,70,48,0.5)' }} />
              <span>{t('gph.error')}</span>
              <button type="button" onClick={() => void q.refetch()} className="font-mono text-[12px]" style={{ color: palette.nodeHot }}>
                {t('gph.retry')}
              </button>
            </div>
          </Overlay>
        )}
        {!q.isPending && !q.isError && data.nodes.length === 0 && <Overlay>{t('gph.empty')}</Overlay>}

        {/* controls: hop + center + legend */}
        <div className="pointer-events-auto absolute left-4 top-4 flex flex-col gap-2.5">
          <div className="flex items-center gap-2 rounded-md px-2 py-1.5" style={{ background: 'rgba(10,10,12,0.5)', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)' }}>
            <span className="pl-1 font-mono text-[9.5px] uppercase tracking-[0.1em]" style={{ color: palette.text, opacity: 0.7 }}>{t('gph.hops')}</span>
            {/* depth still capped at 2 by backend security policy; 'Full' loads the whole graph via /graph/all */}
            <div className="flex gap-0.5">
              {[1, 2].map((d) => (
                <button key={d} type="button" data-testid={`gph-hop-${d}`} onClick={() => { setFull(false); setDepth(d); }} className="h-[22px] w-[22px] rounded-sm font-mono text-[11px] tabular-nums transition-colors" style={!full && depth === d ? { background: 'color-mix(in srgb, var(--sec-graph) 28%, transparent)', color: ACCENT, boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-graph) 45%, transparent)' } : { color: palette.text, background: 'rgba(255,255,255,0.06)' }}>
                  {d}
                </button>
              ))}
              <button type="button" data-testid="gph-hop-full" onClick={() => setFull(true)} className="h-[22px] rounded-sm px-2 font-mono text-[10px] uppercase tracking-[0.06em] transition-colors" style={full ? { background: 'color-mix(in srgb, var(--sec-graph) 28%, transparent)', color: ACCENT, boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--sec-graph) 45%, transparent)' } : { color: palette.text, background: 'rgba(255,255,255,0.06)' }}>
                {t('gph.full')}
              </button>
            </div>
          </div>
          <div className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 font-mono text-[9.5px]" style={{ background: 'rgba(10,10,12,0.5)', color: palette.text, boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)' }}>
            <span className="uppercase tracking-[0.1em] opacity-60">{t('gph.center')}</span>
            <span className="truncate" style={{ maxWidth: 160 }}>{center}</span>
            {center !== DEFAULT_CENTER && (
              <button
                type="button"
                onClick={() => setCenter(DEFAULT_CENTER)}
                aria-label={t('gph.resetCenter', { center: DEFAULT_CENTER })}
                title={t('gph.resetCenter', { center: DEFAULT_CENTER })}
                className="ml-1 grid h-[18px] w-[18px] place-items-center rounded-sm"
                style={{ background: 'rgba(255,255,255,0.08)', color: palette.text }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} width={11} height={11} aria-hidden="true">
                  <path d="M3 12a9 9 0 1 0 3-6.7L3 8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M3 4v4h4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
          </div>
          {selectedIds.size > 0 && (
            <div className="flex items-center justify-between gap-2 rounded-md px-2.5 py-1.5 font-mono text-[9.5px]" style={{ background: 'rgba(10,10,12,0.5)', color: palette.text, boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)' }}>
              <span data-testid="gph-selcount">{t('gph.selected', { count: selectedIds.size })}</span>
              <button type="button" onClick={() => setSelectedIds(new Set())} className="rounded-sm px-1.5 uppercase tracking-[0.08em]" style={{ background: 'rgba(255,255,255,0.08)' }}>
                {t('gph.ctx.clearSelection')}
              </button>
            </div>
          )}
          <div className="flex flex-col gap-1 rounded-md px-2.5 py-2" style={{ background: 'rgba(10,10,12,0.5)', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)' }}>
            {typeLegend.rows.map(([ty, n]) => (
              <span key={ty} className="flex items-center gap-1.5 font-mono text-[9.5px]" style={{ color: palette.text }}>
                <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: ty === '∅' ? FALLBACK : colorFor(ty), boxShadow: `0 0 5px ${ty === '∅' ? FALLBACK : colorFor(ty)}` }} />
                <span className="flex-1">{ty === '∅' ? t('gph.untyped') : ty}</span>
                <span className="opacity-50">{n}</span>
              </span>
            ))}
            {typeLegend.more > 0 && (
              <span className="flex items-center gap-1.5 font-mono text-[9.5px]" style={{ color: palette.text, opacity: 0.6 }}>
                <span className="h-[6px] w-[6px] flex-none rounded-full" style={{ background: FALLBACK }} />
                <span className="flex-1">{t('gph.moreTypes', { count: typeLegend.more })}</span>
              </span>
            )}
          </div>
          <TunePanel open={tuneOpen} onToggle={() => setTuneOpen((o) => !o)} values={tune} onChange={(patch) => setTune((prev) => ({ ...prev, ...patch }))} />
        </div>

        {/* status slab */}
        <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-2 rounded-md px-3 py-1.5 font-mono text-[10px]" style={{ background: 'rgba(10,10,12,0.5)', color: palette.text, boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.08)' }}>
          <span className="h-[7px] w-[7px] rounded-full" style={frozen ? { background: 'var(--ink-4)' } : { background: ACCENT, boxShadow: `0 0 6px ${ACCENT}` }} />
          {frozen ? t('gph.frozen') : t('gph.live')} · {t('gph.status', { count: data.nodes.length })}
        </div>

        {contextMenu && (
          <GraphContextMenu
            menu={contextMenu}
            size={size}
            isAdmin={isAdmin}
            mergeTarget={mergeTarget}
            expanding={expanding}
            hasSelection={selectedIds.size > 0}
            onClose={() => setContextMenu(null)}
            onInspect={(node) => { setSelected(node); setContextMenu(null); }}
            onRecenter={(node) => { recenter(node); setContextMenu(null); }}
            onExpand={(node) => void expandNeighbors(node)}
            onMerge={(node, target) => { setMergeConfirm({ source: node, target }); setContextMenu(null); }}
            onSelectVisible={() => { setSelectedIds(new Set(data.nodes.map((n) => n.id))); setContextMenu(null); }}
            onClearSelection={() => { setSelectedIds(new Set()); setContextMenu(null); }}
          />
        )}

        {mergeConfirm && (
          <MergeConfirmModal
            source={mergeConfirm.source}
            target={mergeConfirm.target}
            pending={merge.isPending}
            onConfirm={doMerge}
            onCancel={() => setMergeConfirm(null)}
          />
        )}

        {selected && <Inspector node={selected} relations={relations} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}
