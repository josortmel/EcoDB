/* EcoDB App — Views 2: Decisions · Ingestion · Ontology · Graph Studio · Settings */
const { useState: v2S } = React;

/* ---------------- Decisions Inbox (split view, why-surfaced, resolve/dismiss/defer) ---------------- */
function DecisionsInbox() {
  const eco = window.useEco();
  const I = window.EcoIcons;
  const items = [
    ...eco.aliasCandidates.map(a => ({ id: a.id, kind: "alias", color: "#6e9ecf", title: `Merge “${a.entity}” → “${a.canonical}”?`, k: `alias candidate · ${a.occ} occurrences`, why: `GLiNER extracted “${a.entity}” ${a.occ} times. It isn't in the entity dictionary but fuzzy-matches the canonical “${a.canonical}” at 0.91.`, ctx: [["new mention", a.entity], ["canonical", a.canonical], ["dictionary", "not present → candidate"]], acts: [["Merge into canonical", "primary", () => eco.approveAlias(a.id)], ["Keep separate", "", () => eco.dismissAlias(a.id)], ["Add as new entity", "", () => eco.dismissAlias(a.id)]] })),
    ...eco.contradictions.map(c => ({ id: c.id, kind: "contra", color: "var(--red)", title: `Contradiction · ${c.topic}`, k: "two memories conflict", why: "Stage 8 (contradiction detection) flagged two memories that assert opposite facts about the same entity within the same project.", ctx: [["memory A", c.a], ["memory B", c.b], ["topic", c.topic]], acts: [["Keep A · supersede B", "primary", () => eco.resolveContra(c.id, "a")], ["Keep B · supersede A", "primary", () => eco.resolveContra(c.id, "b")], ["Defer", "", () => eco.resolveContra(c.id, "defer")]] })),
    { id: "stale-batch", kind: "stale", color: "#c4a86a", title: "118 memories flagged stale", k: "temporal freshness", why: "These memories haven't been referenced or confirmed in over 6 months. Freshness scoring is deprioritising them in retrieval.", ctx: [["count", "118 memories"], ["oldest", "8 months"], ["policy", "auto-flag > 6mo"]], acts: [["Review batch", "primary", () => eco.toast("Stale batch review would open")], ["Archive all", "danger", () => eco.toast("118 memories archived")], ["Keep all fresh", "", () => eco.toast("Marked fresh")]] },
  ];
  const [sel, setSel] = v2S(0);
  const cur = items[Math.min(sel, items.length - 1)] || null;
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Decisions Inbox</h1><div className="sub">Human-in-the-loop review · the system suggests, you decide · {items.length} pending</div></div></div>
      {items.length === 0
        ? <GlassCard><div className="card-msg" style={{ padding: 50 }}><Dot s="ok" anim="pulse" /><span className="m">Queue clear — nothing needs a decision.</span></div></GlassCard>
        : <div className="split">
            <div className="declist">
              {items.map((it, i) => (
                <div className={"decitem" + (i === sel ? " sel" : "")} key={it.id} onClick={() => setSel(i)}>
                  <span className="ic" style={{ color: it.color }}>{it.kind === "alias" ? <I.entity /> : it.kind === "contra" ? <I.warn /> : <I.clock />}</span>
                  <div><div className="dt">{it.title}</div><div className="dk">{it.k}</div></div>
                </div>
              ))}
            </div>
            {cur && <GlassCard accent={cur.color} title={cur.kind === "alias" ? "alias candidate" : cur.kind === "contra" ? "contradiction" : "stale review"} tag={cur.k}>
              <div className="why-box"><div className="wt">why surfaced?</div><div className="wd">{cur.why}</div></div>
              {cur.ctx.map(c => <div className="ctxcard" key={c[0]}><div className="cl">{c[0]}</div><div className="cc">{c[1]}</div></div>)}
              <div className="dwr-btns" style={{ marginTop: 16, flexWrap: "wrap" }}>{cur.acts.map(a => <Button key={a[0]} variant={a[1]} onClick={() => { a[2](); setSel(s => Math.max(0, s - (s >= items.length - 1 ? 1 : 0))); }}>{a[0]}</Button>)}</div>
            </GlassCard>}
          </div>}
    </React.Fragment>
  );
}

/* ---------------- Ingestion (queue + metrics + actions) ---------------- */
function IngestionView() {
  const eco = window.useEco();
  const I = window.EcoIcons;
  const counts = { pending: eco.documents.filter(d => d.status === "pending").length, processing: eco.documents.filter(d => d.status === "processing").length, indexed: eco.documents.filter(d => d.status === "indexed").length, error: eco.documents.filter(d => d.status === "error").length };
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Ingestion</h1><div className="sub">Docling pipeline · parse → chunk (960 tok) → NER → embed → graph link → index · live via SSE</div></div><div className="right"><Button variant="primary"><span style={{ display: "inline-flex", verticalAlign: "-2px", marginRight: 6, width: 14, height: 14 }}><I.plus /></span>Register document</Button></div></div>
      <div className="mstrip">
        <div className="m"><div className="v">{counts.pending}</div><div className="k">pending</div></div>
        <div className="m"><div className="v acc">{counts.processing}</div><div className="k">processing</div></div>
        <div className="m"><div className="v">{counts.indexed}</div><div className="k">indexed</div></div>
        <div className="m"><div className="v" style={{ color: counts.error ? "var(--red)" : null }}>{counts.error}</div><div className="k">error</div></div>
      </div>
      <GlassCard title="document queue" accent="#4FA0A0" variant="flush">
        <div style={{ padding: "8px 8px 12px" }}>
          <div className="rows">{eco.documents.map(d => <window.DocRow key={d.id} d={d} onReindex={eco.reindexDoc} onUnlink={eco.unlinkDoc} />)}</div>
        </div>
      </GlassCard>
    </React.Fragment>
  );
}

/* ---------------- Ontology Console (entities + predicates) ---------------- */
const PREDICATES = [["is_a", "type · transitive", "canonical"], ["part_of", "mereology · transitive", "canonical"], ["depends_on", "causal", "canonical"], ["decided_by", "provenance", "canonical"], ["contradicts", "logical · symmetric", "canonical"], ["supersedes", "temporal", "canonical"], ["mentions", "co-occurrence", "alias → references"], ["related_to", "generic", "deprecated"]];
const ENTITIES = [["Eco Consulting", "organizacion", "Eco, EcoConsulting", 41], ["EcoDB", "producto", "EcoDB v0.9, Eco DB", 88], ["GAMR", "concepto", "GAMR engine", 36], ["Apache AGE", "tecnologia", "AGE", 22], ["Jina v4", "modelo", "Jina-v4, jina", 17], ["GLiNER", "modelo", "gliner", 14]];
function OntologyConsole() {
  const eco = window.useEco();
  const I = window.EcoIcons;
  const [tab, setTab] = v2S("entities");
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Ontology Console</h1><div className="sub">Curate the make-sense layer · entity dictionary + ~100 canonical predicates · the human governs the graph</div></div>
        <div className="tabs"><button className={tab === "entities" ? "on" : ""} onClick={() => setTab("entities")}>Entities<span className="ct">{ENTITIES.length}</span></button><button className={tab === "predicates" ? "on" : ""} onClick={() => setTab("predicates")}>Predicates<span className="ct">98</span></button></div>
      </div>
      <GlassCard variant="flush">
        <div style={{ padding: 8 }}>
          {tab === "entities"
            ? ENTITIES.map(e => (
                <div className="erow" key={e[0]}><span style={{ color: "#6e9ecf", width: 18, height: 18 }}><I.entity /></span>
                  <div><div className="en">{e[0]}</div><div className="al">aliases: {e[2]}</div></div>
                  <Chip>{e[1]}</Chip><span className="badge">{e[3]} refs</span>
                  <div className="eacts"><button className="iconbtn" title="merge" onClick={() => eco.toast("Merge dialog")}><I.merge /></button><button className="iconbtn" title="edit type" onClick={() => eco.toast("Retype")}><I.edit /></button><button className="iconbtn danger" title="stop entity" onClick={() => eco.toast("Added to stop list")}><I.x /></button></div>
                </div>))
            : PREDICATES.map(p => (
                <div className="erow" key={p[0]}><span style={{ color: "var(--grn)", width: 18, height: 18 }}><I.entity /></span>
                  <div><div className="en" style={{ fontFamily: "var(--font-mono)" }}>{p[0]}</div><div className="al">{p[1]}</div></div>
                  <span></span><span className={"badge " + (p[2] === "deprecated" ? "st-error" : "st-indexed")}>{p[2]}</span>
                  <div className="eacts"><button className="iconbtn" title="edit" onClick={() => eco.toast("Edit predicate")}><I.edit /></button></div>
                </div>))}
        </div>
      </GlassCard>
    </React.Fragment>
  );
}

/* ---------------- Graph Studio (full-screen graph + node panel) ---------------- */
const GS_CLUSTERS = [["organizations", "var(--accent)"], ["technologies", "#6e9ecf"], ["concepts", "var(--grn)"], ["documents", "#c4a86a"]];
function GraphStudio() {
  const eco = window.useEco();
  const [node, setNode] = v2S(null);
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Graph Studio</h1><div className="sub">Apache AGE · 1,247 nodes · 8 Louvain clusters · click a node to inspect · hover for labels</div></div><div className="right"><Segmented options={["1 hop", "2 hops", "3 hops"]} value="2 hops" onChange={() => {}} /></div></div>
      <div className="gs">
        <div className="gs-canvas">
          <div className="screen" style={{ flex: 1 }}><KnowledgeGraph onPick={n => setNode(n)} /></div>
        </div>
        <div className="gs-side">
          <GlassCard title="clusters" accent="#4E9E6A" tag="louvain"><div className="legend">{GS_CLUSTERS.map(c => <div className="lg" key={c[0]}><span className="sw" style={{ background: c[1] }}></span>{c[0]}</div>)}</div></GlassCard>
          <GlassCard title="selection" tag={node ? node.type : "—"} className="grow" style={{ flex: 1 }}>
            {node ? <React.Fragment>
              <div className="np"><div className="nm">{node.label}</div><div className="nk">{node.type} · cluster {node.cluster}</div></div>
              <div className="dwr-stats"><div className="dwr-stat"><div className="v">{node.degree}</div><div className="k">connections</div></div><div className="dwr-stat"><div className="v">{node.centrality}</div><div className="k">centrality</div></div></div>
              <div className="dwr-btns" style={{ marginTop: 14 }}><Button variant="primary" onClick={() => eco.toast("Expanding neighbors…")}>Expand neighbors</Button><Button onClick={() => eco.toast("Path mode")}>Path</Button></div>
            </React.Fragment> : <div className="card-msg"><Dot s="idle" /><span className="m">click a node to inspect</span></div>}
          </GlassCard>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ---------------- Settings ---------------- */
function SettingsView() {
  const eco = window.useEco();
  const [flags, setFlags] = v2S({ ultrasearch: true, crossEncoder: true, contradiction: true, autoLink: false });
  const [keyShown, setKeyShown] = v2S(false);
  return (
    <React.Fragment>
      <div className="page-head"><div><h1>Settings</h1><div className="sub">Trust tiers · memory types · entity dictionary · feature flags · API key management</div></div></div>
      <div className="setgrid">
        <GlassCard title="trust tiers" accent="#4E9E6A" tag="retrieval weighting">
          <div className="tiers"><div className="tier high"><div className="tv">1.0×</div><div className="tk">high</div></div><div className="tier"><div className="tv">0.7×</div><div className="tk">medium</div></div><div className="tier low"><div className="tv">0.3×</div><div className="tk">low</div></div></div>
          <div className="ls" style={{ marginTop: 12, color: "var(--ink-3)", fontSize: 11 }}>Multipliers applied to the GAMR composite score by document/memory trust tier.</div>
        </GlassCard>
        <GlassCard title="feature flags" accent="#F5631E" tag="engine">
          <div className="setsec">
            {[["ultrasearch", "UltraSearch", "deep_factor candidate multiplier"], ["crossEncoder", "Cross-encoder rerank", "stage 10 reranking"], ["contradiction", "Contradiction detection", "stage 8"], ["autoLink", "Auto-link entities", "skip human review (not recommended)"]].map(f => (
              <div className="row-line" key={f[0]}><div><div className="ll">{f[1]}</div><div className="ls">{f[2]}</div></div><Toggle on={flags[f[0]]} onChange={() => { setFlags(s => ({ ...s, [f[0]]: !s[f[0]] })); eco.toast(f[1] + (flags[f[0]] ? " disabled" : " enabled")); }} /></div>
            ))}
          </div>
        </GlassCard>
        <GlassCard title="entity dictionary" accent="#5C8FC9" tag="curated">
          <div className="setsec">
            {["Eco Consulting", "EcoDB", "GAMR", "Apache AGE"].map(e => <div className="row-line" key={e}><div className="ll">{e}</div><button className="iconbtn danger" onClick={() => eco.toast("Removed from dictionary")}><window.EcoIcons.x /></button></div>)}
          </div>
          <div className="apikey" style={{ marginTop: 12 }}><input className="field" placeholder="Add canonical entity…" /><Button variant="primary">Add</Button></div>
        </GlassCard>
        <GlassCard title="api key" accent="#8E78BC" tag="v0.9 · per-org">
          <div className="apikey"><code>{keyShown ? "ecodb_7f3a9c1e8b2d4a6f0e5c9b8a7d6e5f4c" : "ecodb_••••••••••••••••••••••••••••••••"}</code><Button onClick={() => setKeyShown(s => !s)}>{keyShown ? "Hide" : "Show"}</Button></div>
          <div className="dwr-btns" style={{ marginTop: 12 }}><Button onClick={() => eco.toast("New key generated")}>Rotate key</Button><Button variant="danger" onClick={() => eco.toast("Key revoked")}>Revoke</Button></div>
          <div className="ls" style={{ marginTop: 12, color: "var(--ink-3)", fontSize: 11 }}>Stored locally (electron-store · safeStorage). Never sent to the renderer.</div>
        </GlassCard>
      </div>
    </React.Fragment>
  );
}

Object.assign(window, { DecisionsInbox, IngestionView, OntologyConsole, GraphStudio, SettingsView });
