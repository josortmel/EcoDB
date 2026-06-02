/* ECODB — knowledge graph: labelled nodes, hover + click to inspect */
const GRAPH_LABELS = [
  "Northwind Logistics", "Q3 Pricing Tier", "Vendor Contracts", "Legal Corpus",
  "Retrieval Pipeline", "BM25 Reranker", "Vector Index", "Embedding Store",
  "Field Onboarding", "Outage #4471", "Async Standups", "OKR 2026",
  "Acme Corp", "Entity Graph", "Support Tickets", "Postmortem Q1",
  "Calendar Agent", "Knowledge Base", "Dedup Engine", "Cluster δ-09",
];
const GRAPH_TYPES = ["Entity", "Document", "Decision", "Topic"];
const GRAPH_RELATED = [
  { lt: "18:04", x: "Vendor contract renewal terms locked for Q3" },
  { lt: "16:52", x: "Reranker migration decision recorded" },
  { lt: "15:30", x: "Entity merged from 3 duplicate references" },
  { lt: "14:11", x: "Reindex completed · 14,208 chunks" },
  { lt: "12:48", x: "Cross-referenced with March postmortem" },
];

function KnowledgeGraph({ onPick }) {
  const ref = React.useRef(null);
  const wrapRef = React.useRef(null);
  const pickRef = React.useRef(onPick);
  React.useEffect(() => { pickRef.current = onPick; });

  React.useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas.getContext("2d");
    let raf, W, H, dpr, hoverNode = null;
    const cssEl = getComputedStyle(document.documentElement);
    const read = (n, f) => (cssEl.getPropertyValue(n).trim() || f);

    const clusters = 4;
    let nodes = [];
    function rebuild() {
      nodes = []; let id = 0;
      for (let c = 0; c < clusters; c++) {
        const cx = (0.18 + 0.64 * (c % 2)) * W;
        const cy = (0.26 + 0.5 * (c < 2 ? 0 : 1)) * H;
        const n = 5 + Math.floor(Math.random() * 3);
        for (let i = 0; i < n; i++) {
          const ang = Math.random() * Math.PI * 2;
          const rad = (0.04 + Math.random() * 0.10) * Math.min(W, H);
          nodes.push({
            id: id, cl: c, bx: cx + Math.cos(ang) * rad, by: cy + Math.sin(ang) * rad,
            x: cx, y: cy, ph: Math.random() * 6.28, r: 1.8 + Math.random() * 2.4,
            hub: i === 0, hot: false, label: GRAPH_LABELS[id % GRAPH_LABELS.length], deg: 0,
          });
          id++;
        }
      }
      const hubs = nodes.filter(n => n.hub);
      hubs[Math.floor(Math.random() * hubs.length)].hot = true;
    }

    let edges = [];
    function buildEdges() {
      edges = [];
      for (let c = 0; c < clusters; c++) {
        const cn = nodes.filter(n => n.cl === c);
        const hub = cn.find(n => n.hub);
        cn.forEach(n => { if (n !== hub) edges.push([hub, n]); });
        if (cn.length > 3) edges.push([cn[1], cn[2]]);
      }
      const hubs = nodes.filter(n => n.hub);
      for (let i = 0; i < hubs.length - 1; i++) edges.push([hubs[i], hubs[i + 1], true]);
      edges.push([hubs[0], hubs[hubs.length - 1], true]);
      nodes.forEach(n => n.deg = 0);
      edges.forEach(([a, b]) => { a.deg++; b.deg++; });
    }

    const pulses = [];
    function spawnPulse() {
      const e = edges[Math.floor(Math.random() * edges.length)];
      pulses.push({ e, t: 0, sp: 0.012 + Math.random() * 0.018, hot: e[0].hot || e[1].hot });
    }

    function resize() {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      const r = wrapRef.current.getBoundingClientRect();
      W = r.width; H = r.height;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      rebuild(); buildEdges();
    }

    function nearest(mx, my) {
      let best = null, bd = 18;
      nodes.forEach(n => { const d = Math.hypot(n.x - mx, n.y - my); if (d < bd) { bd = d; best = n; } });
      return best;
    }
    function toLocal(e) { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * W, (e.clientY - r.top) / r.height * H]; }
    const onMove = e => { const [mx, my] = toLocal(e); hoverNode = nearest(mx, my); canvas.style.cursor = hoverNode ? "pointer" : "default"; };
    const onClick = e => {
      const [mx, my] = toLocal(e); const n = nearest(mx, my); if (!n || !pickRef.current) return;
      pickRef.current({
        kind: "node", label: n.label, type: GRAPH_TYPES[n.cl], cluster: "δ-0" + (n.cl + 1),
        degree: n.deg, centrality: (0.3 + Math.random() * 0.6).toFixed(2), hot: n.hot,
        updated: ["2m", "14m", "1h", "3h"][n.id % 4] + " ago",
        related: [GRAPH_RELATED[n.id % GRAPH_RELATED.length], GRAPH_RELATED[(n.id + 2) % GRAPH_RELATED.length], GRAPH_RELATED[(n.id + 4) % GRAPH_RELATED.length]],
      });
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("click", onClick);

    let t = 0;
    function frame() {
      t += 0.016;
      const node = read("--node", "#e9ebee"), hot = read("--node-hot", "#FF6A2C"),
            edge = read("--edge", "rgba(200,205,212,.16)"), grid = read("--screen-grid", "rgba(255,255,255,.05)");
      ctx.clearRect(0, 0, W, H);

      ctx.strokeStyle = grid; ctx.lineWidth = 1; const gs = 32; ctx.beginPath();
      for (let x = (W % gs) / 2; x < W; x += gs) { ctx.moveTo(x, 0); ctx.lineTo(x, H); }
      for (let y = (H % gs) / 2; y < H; y += gs) { ctx.moveTo(0, y); ctx.lineTo(W, y); }
      ctx.stroke();

      nodes.forEach(n => { n.x = n.bx + Math.sin(t * 0.6 + n.ph) * 4; n.y = n.by + Math.cos(t * 0.5 + n.ph) * 4; });

      edges.forEach(([a, b, bridge]) => {
        const lit = hoverNode && (a === hoverNode || b === hoverNode);
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = lit ? "rgba(255,122,60,.5)" : (a.hot || b.hot) ? "rgba(255,106,44,.3)" : edge;
        ctx.lineWidth = lit ? 1.5 : bridge ? 1.3 : 0.85; ctx.setLineDash(bridge && !lit ? [4, 5] : []); ctx.stroke(); ctx.setLineDash([]);
      });

      for (let i = pulses.length - 1; i >= 0; i--) {
        const p = pulses[i]; p.t += p.sp;
        if (p.t >= 1) { pulses.splice(i, 1); continue; }
        const [a, b] = p.e, x = a.x + (b.x - a.x) * p.t, y = a.y + (b.y - a.y) * p.t;
        const col = p.hot ? hot : node; const g = ctx.createRadialGradient(x, y, 0, x, y, 7);
        g.addColorStop(0, col); g.addColorStop(1, "transparent");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fill();
      }

      nodes.forEach(n => {
        const col = n.hot ? hot : node;
        const hov = n === hoverNode;
        const pulse = n.hub ? 1 + Math.sin(t * 1.5 + n.ph) * 0.16 : 1;
        const r = n.r * pulse * (hov ? 1.4 : 1);
        const gr = r * (n.hot ? 3.2 : 2.1);
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, gr);
        g.addColorStop(0, col); g.addColorStop(0.45, n.hot ? "rgba(255,106,44,.4)" : "rgba(230,234,238,.32)"); g.addColorStop(1, "transparent");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, gr, 0, 7); ctx.fill();
        ctx.fillStyle = col; ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 7); ctx.fill();
        if (hov) {
          ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.globalAlpha = .5;
          ctx.beginPath(); ctx.arc(n.x, n.y, r + 5, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
        }
      });

      // hover label
      if (hoverNode) {
        ctx.font = "11px 'DM Mono', monospace";
        const tw = ctx.measureText(hoverNode.label).width;
        let lx = hoverNode.x + 12, ly = hoverNode.y - 10;
        if (lx + tw + 12 > W) lx = hoverNode.x - tw - 16;
        ctx.fillStyle = "rgba(10,10,12,.78)"; ctx.beginPath();
        ctx.roundRect(lx - 7, ly - 13, tw + 14, 20, 5); ctx.fill();
        ctx.fillStyle = "#f0ece4"; ctx.fillText(hoverNode.label, lx, ly + 1);
      }

      raf = requestAnimationFrame(frame);
    }

    resize();
    const ro = new ResizeObserver(resize); ro.observe(wrapRef.current);
    const pt = setInterval(spawnPulse, 1000); spawnPulse(); frame();
    return () => { cancelAnimationFrame(raf); ro.disconnect(); clearInterval(pt); canvas.removeEventListener("pointermove", onMove); canvas.removeEventListener("click", onClick); };
  }, []);

  return (
    <div className="screen" ref={wrapRef}>
      <canvas ref={ref}></canvas>
      <div className="scan"></div>
      <div className="gl"></div>
      <div className="slab"><span className="dot ok pulse" style={{ width: 8, height: 8 }}></span>graph topology · live · click a node</div>
    </div>
  );
}
window.KnowledgeGraph = KnowledgeGraph;
