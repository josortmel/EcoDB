/* EcoDB App — Phase 2 shell: store + nav + view router */
const { useState: aS, useEffect: aE, useRef: aR } = React;
const VIS_NEXT = { public: "workspace", workspace: "private", private: "public" };

const NAVI = {
  command: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>),
  explorer: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5" strokeLinecap="round"/></svg>),
  graph: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="17" cy="17" r="2"/><circle cx="9" cy="7" r="2"/><path d="M8 16l8-8M9 9l7 7"/></svg>),
  decisions: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 13l3-8h12l3 8v5a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M3 13h5l1 2h6l1-2h5"/></svg>),
  ingestion: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M12 3v10m0 0l-4-4m4 4l4-4M5 17v2a2 2 0 002 2h10a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round"/></svg>),
  ontology: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="6" r="3"/><circle cx="5" cy="18" r="2.5"/><circle cx="19" cy="18" r="2.5"/><path d="M10 8l-3.5 7M14 8l3.5 7"/></svg>),
  settings: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/></svg>),
  insights: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M4 19V5M4 19h16M8 16l3-4 3 2 4-6" strokeLinecap="round" strokeLinejoin="round"/></svg>),
};
function NavItem({ ic, label, active, badge, color, onClick }) {
  const I = NAVI[ic];
  return <button className={"nav-item" + (active ? " on" : "")} style={{ "--nc": color || "var(--accent)" }} onClick={onClick}><I />{label}<span className="nled"></span>{badge ? <span className="badge" style={{ color: "#fff", background: "var(--accent)", textTransform: "none" }}>{badge}</span> : null}</button>;
}
const SECCOL = { command: "#F5631E", explorer: "#5C8FC9", graph: "#4E9E6A", decisions: "#C98A3C", ingestion: "#4FA0A0", ontology: "#8E78BC", settings: "#8A8F9C", insights: "#D98C4A" };

/* drawer host: memory detail OR DrawerPanel(node) */
function AppDrawer() {
  const eco = window.useEco();
  const detail = eco.detail;
  const open = !!detail;
  const [last, setLast] = aS(detail);
  const aRef = aR(null), sRef = aR(null), pos = aR(460);
  aE(() => { if (detail) setLast(detail); }, [detail]);
  aE(() => {
    const target = open ? 0 : 460; let raf;
    const step = () => { const c = pos.current; let n = c + (target - c) * 0.24; if (Math.abs(target - n) < 0.5) n = target; pos.current = n;
      if (aRef.current) aRef.current.style.transform = "translateX(" + n + "px)";
      if (sRef.current) { sRef.current.style.opacity = 1 - n / 460; sRef.current.style.pointerEvents = open ? "auto" : "none"; }
      if (n !== target) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step); return () => cancelAnimationFrame(raf);
  }, [open]);
  const d = detail || last;
  const I = window.EcoIcons;
  const TYC = { decision: "var(--accent)", tecnico: "#6e9ecf", momento: "var(--grn)", observacion: "#c4a86a", referencia: "var(--ink-3)" };
  return (
    <React.Fragment>
      <div className="scrim" ref={sRef} style={{ opacity: 0, pointerEvents: "none" }} onClick={eco.closeDrawer}></div>
      <div className="app-drawer" ref={aRef} style={{ transform: "translateX(460px)" }}>
        {d && d.kind === "mem" && (
          <aside className="drawer inline" style={{ "--dwrk": TYC[d.m.type] }}>
            <div className="dwr-head">
              <div><div className="dwr-kicker"><span className="kdot"></span>memory · {d.m.type}</div><div className="dwr-title">{d.m.text.slice(0, 30)}…</div><div className="dwr-desc">{d.m.ts} · {d.m.agent} · {d.m.vis}</div></div>
              <button className="dwr-close" onClick={eco.closeDrawer}><I.x /></button>
            </div>
            <window.MemoryDetail m={d.m} eco={eco} />
          </aside>
        )}
        {d && d.kind === "node" && <DrawerPanel kind="node" d={d} inline />}
      </div>
    </React.Fragment>
  );
}

function App() {
  const [theme, setTheme] = aS("light");
  const [view, setView] = aS("command");
  const [time, setTime] = aS(new Date());
  const [cmdk, setCmdk] = aS(false);
  const [q, setQ] = aS("");
  const [memories, setMemories] = aS(window.EcoData.memories);
  const [documents, setDocuments] = aS(window.EcoData.documents);
  const [aliasCandidates, setAlias] = aS(window.EcoData.aliasCandidates);
  const [contradictions, setContra] = aS(window.EcoData.contradictions);
  const [detail, setDetail] = aS(null);
  const [toasts, setToasts] = aS([]);

  aE(() => { document.documentElement.setAttribute("data-theme", theme); }, [theme]);
  aE(() => { const t = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(t); }, []);
  aE(() => {
    const k = e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setCmdk(c => !c); } if (e.key === "Escape") { setCmdk(false); setDetail(null); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  aE(() => {
    const m = e => document.querySelectorAll(".card").forEach(p => { const r = p.getBoundingClientRect(); p.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100) + "%"); p.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100) + "%"); });
    window.addEventListener("pointermove", m); return () => window.removeEventListener("pointermove", m);
  }, []);

  const toast = (msg, undo) => { const id = Math.random(); setToasts(t => [...t, { id, msg, undo }]); setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 3600); };
  const eco = {
    stats: window.EcoData.stats, health: window.EcoData.health, activity: window.EcoData.activity,
    memories, documents, aliasCandidates, contradictions, detail,
    go: setView, toast, setDetail, closeDrawer: () => setDetail(null),
    openMem: m => setDetail({ kind: "mem", m }),
    deleteMem: m => { setMemories(ms => ms.map(x => x.id === m.id ? { ...x, deleted: true } : x)); toast("Memory moved to bin", () => setMemories(ms => ms.map(x => x.id === m.id ? { ...x, deleted: false } : x))); },
    cycleVis: m => { const nv = VIS_NEXT[m.vis]; setMemories(ms => ms.map(x => x.id === m.id ? { ...x, vis: nv } : x)); setDetail(d => d && d.kind === "mem" && d.m.id === m.id ? { ...d, m: { ...d.m, vis: nv } } : d); toast("Visibility → " + nv); },
    reindexDoc: d => { setDocuments(ds => ds.map(x => x.id === d.id ? { ...x, status: "processing" } : x)); toast("Re-indexing " + d.name); setTimeout(() => setDocuments(ds => ds.map(x => x.id === d.id ? { ...x, status: "indexed", chunks: x.chunks || 64 } : x)), 1600); },
    unlinkDoc: d => { setDocuments(ds => ds.filter(x => x.id !== d.id)); toast("Unlinked " + d.name); },
    approveAlias: id => { setAlias(a => a.filter(x => x.id !== id)); toast("Entities merged"); },
    dismissAlias: id => { setAlias(a => a.filter(x => x.id !== id)); toast("Kept separate"); },
    resolveContra: (id, c) => { setContra(x => x.filter(y => y.id !== id)); toast(c === "defer" ? "Deferred" : "Contradiction resolved"); },
  };

  const T = time.toLocaleTimeString("en-US", { hour12: false });
  const D = time.toLocaleDateString("en-US", { weekday: "short", day: "2-digit", month: "short" });
  const inboxCount = aliasCandidates.length + contradictions.length + 118;
  const cmdkResults = (q ? memories.filter(m => !m.deleted && m.text.toLowerCase().includes(q.toLowerCase())) : memories.filter(m => !m.deleted)).slice(0, 6).map(m => ({ type: "memory", title: m.text, sub: m.type + " · " + m.agent, kind: "memory" }));

  return (
    <window.EcoCtx.Provider value={eco}>
      <div className="app">
        <nav className="nav">
          <div className="brand"><div className="logo"><svg viewBox="0 0 32 32" aria-label="Eco Consulting"><rect x="2" y="2" width="28" height="28" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8"/><line x1="8" y1="10" x2="24" y2="10" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square"/><line x1="8" y1="16" x2="20" y2="16" stroke="var(--accent)" strokeWidth="2.4" strokeLinecap="square"/><line x1="8" y1="22" x2="24" y2="22" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square"/></svg></div><div><div className="nm">EcoDB</div></div></div>
          <div className="nav-sec">workspace</div>
          <NavItem ic="command" label="Command Center" color={SECCOL.command} active={view === "command"} onClick={() => setView("command")} />
          <NavItem ic="explorer" label="Knowledge Explorer" color={SECCOL.explorer} active={view === "explorer"} onClick={() => setView("explorer")} />
          <NavItem ic="graph" label="Graph Studio" color={SECCOL.graph} active={view === "graph"} onClick={() => setView("graph")} />
          <NavItem ic="decisions" label="Decisions Inbox" color={SECCOL.decisions} badge={inboxCount} active={view === "decisions"} onClick={() => setView("decisions")} />
          <div className="nav-sec">governance</div>
          <NavItem ic="ingestion" label="Ingestion" color={SECCOL.ingestion} active={view === "ingestion"} onClick={() => setView("ingestion")} />
          <NavItem ic="ontology" label="Ontology Console" color={SECCOL.ontology} active={view === "ontology"} onClick={() => setView("ontology")} />
          <NavItem ic="settings" label="Settings" color={SECCOL.settings} active={view === "settings"} onClick={() => setView("settings")} />
          <div className="nav-grow"></div>
          <NavItem ic="insights" label="Insights" color={SECCOL.insights} active={view === "insights"} onClick={() => setView("insights")} />
          <div className="nav-user" style={{ marginTop: 8 }}><div className="av">L</div><div className="who"><div className="n">Lienzo</div><div className="r">superuser · all workspaces</div></div></div>
        </nav>

        <div className="workzone">
          <div className="appbar">
            <SearchField value={q} placeholder="Search 1,847 memories · ⌘K for command palette" resultCount={q ? memories.filter(m => !m.deleted && m.text.toLowerCase().includes(q.toLowerCase())).length : undefined} onChange={setQ} onClear={() => setQ("")} />
            <div className="spacer"></div>
            <StatusPill services={6} healthy={6} latency="48ms" />
            <div className="ctx"><span>{T}</span><b>{D}</b></div>
            <ThemeToggle theme={theme} onToggle={() => setTheme(t => t === "dark" ? "light" : "dark")} />
          </div>
          <div className="main">
            {view === "command" ? <window.CommandCenter />
              : view === "explorer" ? <window.KnowledgeExplorer />
              : view === "insights" ? <window.InsightsView />
              : view === "decisions" ? <window.DecisionsInbox />
              : view === "graph" ? <window.GraphStudio />
              : view === "ingestion" ? <window.IngestionView />
              : view === "ontology" ? <window.OntologyConsole />
              : <window.SettingsView />}
          </div>
        </div>

        {cmdk && <div className="cmdk-overlay" onClick={e => { if (e.target.classList.contains("cmdk-overlay")) setCmdk(false); }}><CmdK query={q} results={cmdkResults} state={q ? "results" : "empty"} selected={0} /></div>}
        <AppDrawer />
        <div className="toasts">{toasts.map(t => <div className="toast" key={t.id}><Dot s="ok" />{t.msg}{t.undo && <span className="undo" onClick={() => { t.undo(); setToasts(x => x.filter(y => y.id !== t.id)); }}>undo</span>}</div>)}</div>
      </div>
    </window.EcoCtx.Provider>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
