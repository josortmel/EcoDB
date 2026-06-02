/* EcoDB App — data layer + store context + shared icons */
window.EcoCtx = React.createContext(null);
window.useEco = () => React.useContext(window.EcoCtx);

const uid = (p) => p + "-" + Math.random().toString(36).slice(2, 7);

window.EcoIcons = {
  edit: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 20h4L18.5 9.5a2.1 2.1 0 00-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/></svg>),
  trash: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg>),
  eye: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>),
  refresh: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M20 11a8 8 0 10-1.5 5.5M20 5v6h-6" strokeLinecap="round"/></svg>),
  unlink: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M9 15l6-6M8 12l-2 2a3 3 0 004 4l2-2M16 12l2-2a3 3 0 00-4-4l-2 2"/></svg>),
  check: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>),
  x: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round"/></svg>),
  merge: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M7 4v6a5 5 0 005 5h5M17 12l3 3-3 3" strokeLinecap="round" strokeLinejoin="round"/></svg>),
  clock: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2" strokeLinecap="round"/></svg>),
  memory: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9"/></svg>),
  doc: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/></svg>),
  entity: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="7" r="3"/><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="17" r="2.5"/><path d="M10 9l-3 5M14 9l3 5"/></svg>),
  warn: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17h.01" strokeLinecap="round"/></svg>),
  plus: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 5v14M5 12h14" strokeLinecap="round"/></svg>),
  arrow: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M7 17L17 7M9 7h8v8" strokeLinecap="round" strokeLinejoin="round"/></svg>),
};

const GAMR_STAGES = ["classify", "embed", "vector", "bm25", "graph", "source", "fresh", "contra", "composite", "rerank"];

window.EcoData = {
  stats: { memories: 1847, documents: 142, nodes: 1247, triples: 3291, agents_on: 3, agents_total: 4 },
  memories: [
    { id: uid("m"), ts: "14:33", text: "Multi-tenant spec aprobado para v0.9 — aislamiento por namespace, claves por org", type: "decision", tags: ["v0.9", "multi-tenant"], agent: "Lienzo", vis: "public", trust: "high", stale: false, score: [.9, .82, .88, .61, .5, 1, .99, 1, .91, .76] },
    { id: uid("m"), ts: "14:08", text: "Chunking de sesiones en ventanas de 5 turnos → +19.9% Recall@5 en LoCoMo", type: "tecnico", tags: ["ingest", "gamr"], agent: "Prima", vis: "workspace", trust: "high", stale: false, score: [.8, .79, .84, .7, .42, 1, .95, 1, .88, .72] },
    { id: uid("m"), ts: "13:40", text: "GLiNER + diccionario de entidades: el match del diccionario tiene prioridad sobre NER", type: "tecnico", tags: ["ner", "graph"], agent: "Hilo", vis: "workspace", trust: "med", stale: false, score: [.7, .74, .8, .55, .61, .9, .9, 1, .82, .6] },
    { id: uid("m"), ts: "12:51", text: "Conflicto detectado: dos memorias contradictorias sobre el schema de la tabla graph_clusters", type: "observacion", tags: ["gamr", "contradiction"], agent: "Prima", vis: "workspace", trust: "low", stale: false, contradiction: true, score: [.6, .7, .76, .5, .55, .85, .7, .4, .7, .55] },
    { id: uid("m"), ts: "11:22", text: "Decisión: graph bonus = 5% del score GAMR, deliberadamente bajo (exploración, no ranking)", type: "decision", tags: ["graph"], agent: "Lienzo", vis: "public", trust: "high", stale: false, score: [.85, .8, .8, .6, .9, 1, .98, 1, .9, .7] },
    { id: uid("m"), ts: "10:09", text: "Docling parseó 12 PDFs nuevos → 1,440 chunks indexados (960 tokens cada uno)", type: "momento", tags: ["docling", "ingest"], agent: "Hilo", vis: "workspace", trust: "high", stale: false, score: [.5, .6, .7, .65, .3, 1, 1, 1, .75, .5] },
    { id: uid("m"), ts: "09:15", text: "Referencia: LoCoMo benchmark (Maharana et al., ACL 2024) — 1,982 queries, 10 conversaciones", type: "referencia", tags: ["eval"], agent: "Prima", vis: "public", trust: "high", stale: true, score: [.4, .55, .62, .58, .2, 1, .4, 1, .6, .45] },
    { id: uid("m"), ts: "08:47", text: "Jina v4: texto e imagen en el mismo espacio de 512 dimensiones (cross-modal search)", type: "tecnico", tags: ["multimodal", "embeddings"], agent: "Hilo", vis: "private", trust: "high", stale: false, score: [.7, .85, .82, .5, .35, 1, .92, 1, .85, .68] },
  ],
  documents: [
    { id: uid("d"), name: "README v0.9.md", ext: "md", status: "indexed", chunks: 142, size: "86 KB", trust: "high" },
    { id: uid("d"), name: "EcoDB_fase6_plan.md", ext: "md", status: "indexed", chunks: 88, size: "54 KB", trust: "high" },
    { id: uid("d"), name: "LoCoMo_results.pdf", ext: "pdf", status: "processing", chunks: 0, size: "1.2 MB", trust: "med" },
    { id: uid("d"), name: "governance_brief.docx", ext: "docx", status: "pending", chunks: 0, size: "340 KB", trust: "med" },
    { id: uid("d"), name: "standup_2026-05-30.m4a", ext: "audio", status: "pending", chunks: 0, size: "8.4 MB", trust: "low" },
    { id: uid("d"), name: "ontology_v2.pptx", ext: "pptx", status: "error", chunks: 0, size: "2.1 MB", trust: "low" },
  ],
  aliasCandidates: [
    { id: uid("a"), entity: "ACME Inc", canonical: "Acme Corp", occ: 7 },
    { id: uid("a"), entity: "EcoDB v0.9", canonical: "EcoDB", occ: 12 },
    { id: uid("a"), entity: "Jina-v4", canonical: "Jina v4", occ: 5 },
  ],
  contradictions: [
    { id: uid("c"), topic: "graph_clusters schema", a: "node_id es PK", b: "cluster_id es PK", aId: 3 },
  ],
  activity: [
    { ts: "14:33", ic: "memory", x: "Memoria guardada · auto-enlazó 4 entidades", who: "Lienzo" },
    { ts: "14:31", ic: "doc", x: "Documento indexado · README v0.9 (142 chunks)", who: "Docling" },
    { ts: "14:28", ic: "entity", x: "Candidato de alias detectado · ACME Inc → Acme Corp", who: "GLiNER" },
    { ts: "14:24", ic: "warn", x: "Contradicción marcada · graph_clusters schema", who: "GAMR" },
    { ts: "14:19", ic: "memory", x: "Búsqueda · deep_factor 4 (UltraSearch)", who: "Prima" },
  ],
  health: [
    { k: "memorias frescas", v: 0.94, c: "var(--grn)" },
    { k: "entidades curadas", v: 0.88, c: "var(--grn)" },
    { k: "relaciones confirmadas", v: 0.72, c: "#c4a86a" },
    { k: "documentos de confianza", v: 0.91, c: "var(--grn)" },
  ],
};
window.GAMR_STAGES = GAMR_STAGES;
