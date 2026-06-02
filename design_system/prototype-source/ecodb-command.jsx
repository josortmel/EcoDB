/* EcoDB App — Command Center (operative home) · Insights · stubs */
const { useState: cmS, useEffect: cmE } = React;

function StatCard({ lab, value, unit, sub, accent, onClick }) {
  const I = window.EcoIcons;
  return (
    <div className="card statcard" onClick={onClick}>
      <div className="top"><span className="lab">{lab}</span><span className="arrow"><I.arrow /></span></div>
      <div className="num" style={accent ? { color: "var(--accent)" } : null}>{value}{unit && <span className="u">{unit}</span>}</div>
      <div className="sub">{sub}</div>
    </div>
  );
}

function ActivityFeed() {
  const eco = window.useEco();
  const [items, setItems] = cmS(eco.activity);
  cmE(() => {
    const pool = [
      { ic: "memory", x: "Memoria guardada · cluster δ-09", who: "Hilo" },
      { ic: "entity", x: "Entidad fusionada · Jina-v4 → Jina v4", who: "GLiNER" },
      { ic: "doc", x: "Reindexado · governance_brief.docx", who: "Docling" },
      { ic: "memory", x: "Búsqueda GAMR · 5 resultados", who: "Prima" },
      { ic: "warn", x: "Memoria marcada stale · 6 meses", who: "Sentinel" },
    ];
    const t = setInterval(() => {
      const now = new Date(); const ts = String(now.getHours()).padStart(2, "0") + ":" + String(now.getMinutes()).padStart(2, "0");
      setItems(i => [{ ...pool[Math.floor(Math.random() * pool.length)], ts }, ...i].slice(0, 9));
    }, 5000);
    return () => clearInterval(t);
  }, []);
  const I = window.EcoIcons;
  return (
    <div className="activity h-list">
      {items.map((a, i) => { const Ic = I[a.ic] || I.memory; return (
        <div className="act" key={a.x + i}><span className="t">{a.ts}</span><span className="ic"><Ic /></span><div><div className="x">{a.x}</div><div className="who">{a.who}</div></div></div>
      ); })}
    </div>
  );
}

function HealthPanel() {
  const eco = window.useEco();
  return (
    <div className="health">
      {eco.health.map(h => (
        <div className="hrow" key={h.k}><span className="hl">{h.k}</span><span className="meter"><i style={{ width: Math.round(h.v * 100) + "%", background: h.c }}></i></span><span className="hv">{Math.round(h.v * 100)}%</span></div>
      ))}
    </div>
  );
}

function AttentionPanel() {
  const eco = window.useEco();
  const I = window.EcoIcons;
  const total = eco.aliasCandidates.length + eco.contradictions.length + 118;
  return (
    <GlassCard title="attention inbox" accent="#C98A3C" control={<span className="cbadge2 hot">{total}</span>}>
      <div className="inbox" style={{ marginBottom: 12 }}>
        <div className="inbox-item"><Dot s="on" anim="pulse" /><span className="il">stale memories</span><span className="cbadge2 hot">118</span></div>
        <div className="inbox-item"><Dot s="on" anim="pulse" /><span className="il">alias candidates · GLiNER</span><span className="cbadge2 hot">{eco.aliasCandidates.length}</span></div>
        <div className="inbox-item"><Dot s="on" anim="pulse" /><span className="il">contradictions</span><span className="cbadge2 hot">{eco.contradictions.length}</span></div>
        <div className="inbox-item zero"><Dot s="idle" /><span className="il">low-trust documents</span><span className="cbadge2">2</span></div>
      </div>
      <div className="title" style={{ marginBottom: 8 }}>needs a decision</div>
      {eco.aliasCandidates.length === 0 && eco.contradictions.length === 0
        ? <div className="dec-empty"><Dot s="ok" anim="pulse" /><span className="card-msg"><span className="m">queue clear — nothing to review</span></span></div>
        : <React.Fragment>
            {eco.aliasCandidates.slice(0, 2).map(a => (
              <div className="dec" key={a.id}>
                <span className="ic" style={{ width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center", background: "var(--card-bg)", boxShadow: "var(--elev)", color: "#6e9ecf", flex: "none" }}><I.entity /></span>
                <div className="body">
                  <div className="why">alias candidate · {a.occ} occurrences</div>
                  <div className="prop">Merge <b>{a.entity}</b> into <b>{a.canonical}</b>?</div>
                  <div className="acts">
                    <Button size="sm" variant="primary" onClick={() => eco.approveAlias(a.id)}>Merge</Button>
                    <Button size="sm" onClick={() => eco.dismissAlias(a.id)}>Keep separate</Button>
                  </div>
                </div>
              </div>
            ))}
            {eco.contradictions.map(c => (
              <div className="dec" key={c.id}>
                <span className="ic" style={{ width: 26, height: 26, borderRadius: 8, display: "grid", placeItems: "center", background: "var(--card-bg)", boxShadow: "var(--elev)", color: "var(--red)", flex: "none" }}><I.warn /></span>
                <div className="body">
                  <div className="why">contradiction · {c.topic}</div>
                  <div className="prop">Which is valid — “{c.a}” or “{c.b}”?</div>
                  <div className="acts">
                    <Button size="sm" variant="primary" onClick={() => eco.resolveContra(c.id, "a")}>Keep A</Button>
                    <Button size="sm" variant="primary" onClick={() => eco.resolveContra(c.id, "b")}>Keep B</Button>
                    <Button size="sm" onClick={() => eco.resolveContra(c.id, "defer")}>Defer</Button>
                  </div>
                </div>
              </div>
            ))}
          </React.Fragment>}
    </GlassCard>
  );
}

function CommandCenter() {
  const eco = window.useEco();
  const s = eco.stats;
  return (
    <React.Fragment>
      <div className="page-head">
        <div><h1>Command Center</h1><div className="sub">Eco Consulting · workspace overview · {s.agents_on}/{s.agents_total} agents online · what needs your attention today</div></div>
      </div>
      <div className="bento">
        <div className="col-3"><StatCard lab="Memories" value={s.memories.toLocaleString()} sub="+23 today · 118 stale" accent onClick={() => eco.go("explorer")} /></div>
        <div className="col-3"><StatCard lab="Documents" value={s.documents} sub="+4 today · 2 in queue" onClick={() => eco.go("explorer")} /></div>
        <div className="col-3"><StatCard lab="Graph" value="1,247" unit=" nodes" sub={s.triples.toLocaleString() + " triples · 98 predicates"} onClick={() => eco.go("graph")} /></div>
        <div className="col-3"><StatCard lab="Agents" value={s.agents_on + "/" + s.agents_total} sub="Lienzo · Hilo · Prima online" onClick={() => eco.go("governance")} /></div>

        <div className="col-5 row-2"><AttentionPanel /></div>
        <div className="col-4 row-2">
          <GlassCard title="activity" accent="#5C8FC9" tag="live · SSE"><ActivityFeed /></GlassCard>
        </div>
        <div className="col-3">
          <GlassCard title="knowledge health" accent="#4E9E6A" tag="salud"><HealthPanel /></GlassCard>
        </div>
        <div className="col-3">
          <GlassCard title="ingestion" accent="#4FA0A0" tag="docling">
            <div className="life">
              <div className="stg"><div className="v">2</div><div className="k">pending</div></div>
              <div className="stg proc"><div className="v">1</div><div className="k">processing</div></div>
              <div className="stg"><div className="v">142</div><div className="k">indexed</div></div>
              <div className="stg err"><div className="v">1</div><div className="k">error</div></div>
            </div>
            <div style={{ marginTop: 12 }}><Button variant="tint" onClick={() => eco.go("explorer")}>Open ingestion queue →</Button></div>
          </GlassCard>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ---------------- Insights (the old metrics view — kept for the future reel) ---------------- */
const seedI = (n, f) => Array.from({ length: n }, (_, i) => f(i));
const GAMR_I = [{ n: "classify", ms: 4 }, { n: "embed", ms: 9 }, { n: "vector", ms: 7 }, { n: "bm25", ms: 5 }, { n: "graph", ms: 6 }, { n: "source", ms: 3 }, { n: "fresh", ms: 2 }, { n: "contra", ms: 4 }, { n: "composite", ms: 3 }, { n: "rerank", ms: 5 }];
const SVCS = [["postgres", "storage · vector · graph"], ["api", "FastAPI · GAMR"], ["embeddings", "Jina v4 (GPU)"], ["ner", "GLiNER"], ["mcp", "MCP · 22 tools"], ["llm", "Qwen 2.5 3B"]];

function InsightsView() {
  const [lit, setLit] = cmS(0);
  cmE(() => { const t = setInterval(() => setLit(l => (l + 1) % 10), 360); return () => clearInterval(t); }, []);
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Insights</h1><div className="sub">Engine metrics — for presentations & the launch reel, not day-to-day work</div></div></div>
      <div className="bento">
        <div className="col-8">
          <GlassCard title="GAMR pipeline" tag="10-stage · graph-augmented multimodal retrieval">
            <div className="gamr">{GAMR_I.map((g, i) => <div className={"gamr-stage" + (i === lit ? " lit" : "")} key={g.n}><div className="pip">{i + 1}</div><div className="nm">{g.n}</div><div className="ms">{g.ms}ms</div></div>)}</div>
            <div className="gamr-foot"><div className="big">48<span className="u">ms p95</span></div><div className="qtype"><span className="qt on">factual</span><span className="qt">analytical</span><span className="qt">historical</span><span className="qt">contextual</span></div></div>
          </GlassCard>
        </div>
        <div className="col-4 row-2"><GlassCard title="services" tag="6/6 healthy"><div className="svc">{SVCS.map(s => <div className="svc-row" key={s[0]}><Dot s="ok" anim="pulse" /><span className="n">{s[0]}</span><span className="role">{s[1]}</span></div>)}</div></GlassCard></div>
        <div className="col-4"><GlassCard title="retrieval quality" tag="recall@5 · LoCoMo"><div className="chart-big"><span className="v">0.922</span><span className="meta">K=20</span></div><div className="h-chart"><AreaChart data={seedI(28, i => 90 + Math.sin(i / 3) * 1.6 + Math.random() * 1.2)} min={84} max={97} band={[90, 94]} tipFmt={v => (v / 100).toFixed(3)} /></div></GlassCard></div>
        <div className="col-4"><GlassCard title="search latency" tag="p50 · full GAMR"><div className="chart-big"><span className="v">44<span className="u">ms</span></span><span className="meta">p95 48ms</span></div><div className="h-chart"><AreaChart data={seedI(28, i => 42 + Math.sin(i / 4) * 3 + Math.random() * 3)} min={30} max={60} unit="ms" tipFmt={v => Math.round(v)} /></div></GlassCard></div>
      </div>
    </React.Fragment>
  );
}

function StubView({ title, desc, tags }) {
  const I = window.EcoIcons;
  return (
    <div className="view-stub">
      <div className="ico"><I.entity /></div>
      <h2>{title}</h2><p>{desc}</p>
      <div className="tagrow">{tags.map(t => <Chip key={t}>{t}</Chip>)}</div>
      <span className="kbd-hint" style={{ marginTop: 10 }}>Command Center + Knowledge Explorer built first · this screen lands next</span>
    </div>
  );
}

Object.assign(window, { CommandCenter, InsightsView, StubView });
