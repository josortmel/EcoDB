// Shared types + pure helpers for the Graph Studio pieces (split out of
// GraphStudio.tsx in FB-GRAPH4 so the page stays small).

export type NodeId = number | string;
export type GNode = { id: NodeId; name: string; type?: string | null; degree: number; x?: number; y?: number; fx?: number; fy?: number; hot?: boolean };
export type GLink = { source: NodeId | GNode; target: NodeId | GNode; predicate: string };

// react-force-graph's imperative handle (only the methods we use).
export type FgHandle = {
  zoomToFit: (ms?: number, pad?: number) => void;
  d3ReheatSimulation: () => void;
  graph2ScreenCoords: (x: number, y: number) => { x: number; y: number };
  d3Force: (name: string) => { strength?: (v: number) => unknown; distance?: (v: number) => unknown } | undefined;
};

// Official 12-type palette (Lienzo, design authority) + a neutral fallback for
// null / unknown types.
export const TYPE_COLOR: Record<string, string> = {
  persona: '#E86A9E',
  agente_ia: '#D4723A',
  proyecto: '#4E9E6A',
  tecnologia: '#8E78BC',
  producto: '#4FA0A0',
  concepto: '#5C8FC9',
  organizacion: '#D98C4A',
  modelo_ia: '#6FC2E0',
  artefacto: '#C4A86A',
  metodologia: '#C079E0',
  lugar: '#8FB96A',
  evento: '#DE6B6B',
};
export const FALLBACK = '#8a8f9c';
export const colorFor = (type?: string | null): string => (type && TYPE_COLOR[type]) || FALLBACK;
export const nodeRadius = (deg: number) => 2 + Math.min(7, deg * 0.3);
export const endId = (e: NodeId | GNode): NodeId => (typeof e === 'object' ? e.id : e);

// Full circle in radians — shared by every canvas arc.
export const TAU = Math.PI * 2;

// Stable dedup key for an edge (source-target-predicate).
export const linkKey = (l: GLink): string => `${endId(l.source)}-${endId(l.target)}-${l.predicate}`;

export function hexToRgba(hex: string, a: number): string {
  let m = hex.replace('#', '');
  if (m.length === 3) m = m[0] + m[0] + m[1] + m[1] + m[2] + m[2]; // #rgb → #rrggbb
  const r = parseInt(m.slice(0, 2), 16);
  const g = parseInt(m.slice(2, 4), 16);
  const b = parseInt(m.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}
