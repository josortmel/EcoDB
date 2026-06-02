/* EcoDB App — Knowledge Explorer (functional: search · filter · CRUD) */
const { useState: exS } = React;
const VIS_CYCLE = { public: "workspace", workspace: "private", private: "public" };

function MemRow({ m, query, onOpen, onDelete, onVis }) {
  const I = window.EcoIcons;
  return (
    <div className="trow mem" onClick={() => onOpen(m)}>
      <Dot s={"t-" + m.type} />
      <div className="main">
        <div className="ttl">{highlight(m.text, query)}</div>
        <div className="meta">
          <span>{m.ts}</span><span>·</span><span>{m.agent}</span><span>·</span><span>{m.type}</span>
          {m.tags.map(t => <Chip key={t}>{t}</Chip>)}
        </div>
      </div>
      {m.stale ? <span className="badge stale">stale</span> : <span className={"badge trust-" + (m.trust === "med" ? "med" : m.trust)}>{m.trust} trust</span>}
      <span className={"badge vis-" + m.vis}>{m.vis}</span>
      <div className="rowacts" onClick={e => e.stopPropagation()}>
        <button className="iconbtn" title="cambiar visibilidad" onClick={() => onVis(m)}><I.eye /></button>
        <button className="iconbtn" title="editar" onClick={() => onOpen(m)}><I.edit /></button>
        <button className="iconbtn danger" title="enviar a papelera" onClick={() => onDelete(m)}><I.trash /></button>
      </div>
    </div>
  );
}

function DocRow({ d, onReindex, onUnlink }) {
  const I = window.EcoIcons;
  return (
    <div className="trow doc">
      <span className="docico"><I.doc /></span>
      <div className="main">
        <div className="ttl">{d.name}</div>
        <div className="meta"><span>{d.ext.toUpperCase()}</span><span>·</span><span>{d.size}</span><span>·</span><span>{d.chunks} chunks</span></div>
      </div>
      <span className={"badge trust-" + (d.trust === "med" ? "med" : d.trust)}>{d.trust}</span>
      <span className={"badge st-" + d.status}>{d.status}</span>
      <div className="rowacts" onClick={e => e.stopPropagation()}>
        <button className="iconbtn" title="reindexar" onClick={() => onReindex(d)}><I.refresh /></button>
        <button className="iconbtn danger" title="desvincular" onClick={() => onUnlink(d)}><I.unlink /></button>
      </div>
    </div>
  );
}

function KnowledgeExplorer() {
  const eco = window.useEco();
  const [tab, setTab] = exS("memories");
  const [q, setQ] = exS("");
  const [fType, setFType] = exS(null);
  const [fVis, setFVis] = exS(null);
  const [fStale, setFStale] = exS(false);

  const mems = eco.memories.filter(m => !m.deleted)
    .filter(m => !q || m.text.toLowerCase().includes(q.toLowerCase()) || m.tags.some(t => t.includes(q.toLowerCase())))
    .filter(m => !fType || m.type === fType)
    .filter(m => !fVis || m.vis === fVis)
    .filter(m => !fStale || m.stale);
  const docs = eco.documents.filter(d => !q || d.name.toLowerCase().includes(q.toLowerCase()));
  const types = ["decision", "tecnico", "momento", "observacion", "referencia"];

  return (
    <React.Fragment>
      <div className="page-head">
        <div><h1>Knowledge Explorer</h1><div className="sub">GAMR search across {eco.memories.length} memories and {eco.documents.length} documents · text, images and chunks ranked together</div></div>
        <div className="tabs">
          <button className={tab === "memories" ? "on" : ""} onClick={() => setTab("memories")}>Memories<span className="ct">{eco.memories.filter(m => !m.deleted).length}</span></button>
          <button className={tab === "documents" ? "on" : ""} onClick={() => setTab("documents")}>Documents<span className="ct">{eco.documents.length}</span></button>
        </div>
      </div>

      <GlassCard variant="flush">
        <div style={{ padding: "16px 16px 4px" }}>
          <div className="toolbar">
            <SearchField value={q} placeholder={tab === "memories" ? "Search memories · GAMR · deep_factor 4" : "Search documents"} resultCount={q ? (tab === "memories" ? mems.length : docs.length) : undefined} onChange={setQ} onClear={() => setQ("")} />
            {tab === "memories" && <React.Fragment>
              <button className={"fchip" + (fStale ? " on" : "")} onClick={() => setFStale(s => !s)}><span className="cv">⏱</span>stale</button>
              {types.map(t => <button key={t} className={"fchip" + (fType === t ? " on" : "")} onClick={() => setFType(fType === t ? null : t)}><Dot s={"t-" + t} />{t}</button>)}
              <button className={"fchip" + (fVis ? " on" : "")} onClick={() => setFVis(fVis === "public" ? "private" : fVis === "private" ? "workspace" : fVis === "workspace" ? null : "public")}><span className="cv">visibility:</span>{fVis || "all"}</button>
            </React.Fragment>}
          </div>
        </div>
        <div style={{ padding: "0 8px 8px" }}>
          <div className="result-count" style={{ padding: "0 8px" }}>{tab === "memories" ? mems.length : docs.length} results{(q || fType || fVis || fStale) ? " · filtered" : ""}</div>
          <div className="rows">
            {tab === "memories"
              ? (mems.length === 0 ? <div className="feed-empty" style={{ padding: 24 }}>No memories match your filters.</div>
                : mems.map(m => <MemRow key={m.id} m={m} query={q} onOpen={eco.openMem} onDelete={eco.deleteMem} onVis={eco.cycleVis} />))
              : docs.map(d => <DocRow key={d.id} d={d} onReindex={eco.reindexDoc} onUnlink={eco.unlinkDoc} />)}
          </div>
        </div>
      </GlassCard>
    </React.Fragment>
  );
}

/* memory detail body for the drawer (score_breakdown + trust warnings + edit) */
function MemoryDetail({ m, eco }) {
  const I = window.EcoIcons;
  return (
    <div className="dwr-body">
      {m.contradiction && <div className="warn"><I.warn /><div className="w">Contradiction flagged — this memory conflicts with another on the same topic. Resolve in the Decisions inbox.</div></div>}
      {m.stale && <div className="warn" style={{ background: "rgba(196,168,106,.1)", boxShadow: "inset 0 0 0 1px rgba(196,168,106,.3)" }}><span style={{ color: "#c4a86a" }}><I.clock /></span><div className="w">Marked stale — temporal freshness scoring deprioritises this memory.</div></div>}
      <div className="dwr-sec"><div className="title">Content</div><div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--ink-1)" }}>{m.text}</div></div>
      <div className="dwr-stats">
        <div className="dwr-stat"><div className="v">{m.agent}</div><div className="k">author</div></div>
        <div className="dwr-stat"><div className="v">{m.type}</div><div className="k">type</div></div>
        <div className="dwr-stat"><div className="v" style={{ textTransform: "capitalize" }}>{m.vis}</div><div className="k">visibility</div></div>
        <div className="dwr-stat"><div className="v" style={{ textTransform: "capitalize" }}>{m.trust}</div><div className="k">trust tier</div></div>
      </div>
      <div className="dwr-sec"><div className="title">GAMR score breakdown · 10 stages</div>
        <div className="score">{window.GAMR_STAGES.map((s, i) => <div className="srow" key={s}><span className="sn">{s}</span><span className="sbar"><i style={{ width: Math.round(m.score[i] * 100) + "%" }}></i></span><span className="sv">{m.score[i].toFixed(2)}</span></div>)}</div>
      </div>
      <div className="dwr-sec"><div className="title">Tags</div><div className="dwr-tags">{m.tags.map(t => <Chip key={t}>{t}</Chip>)}</div></div>
      <div className="dwr-btns">
        <Button variant="primary" onClick={() => eco.toast("Edit form would open here")}>Edit memory</Button>
        <Button onClick={() => eco.cycleVis(m)}>Visibility: {m.vis}</Button>
        <Button variant="danger" onClick={() => { eco.deleteMem(m); eco.setDetail(null); }}>Bin</Button>
      </div>
    </div>
  );
}
window.KnowledgeExplorer = KnowledgeExplorer;
window.MemoryDetail = MemoryDetail;
window.DocRow = DocRow;
