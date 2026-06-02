/* ECODB KIT — search, command palette, drawer, topbar */
const { useState: oS } = React;

/* ---------- B1 SearchField ---------- */
function SearchField({ value = "", placeholder = "Search…", resultCount, loading, focus, disabled, lg, onChange, onClear }) {
  const cls = ["search", lg ? "lg" : "", focus ? "is-focus" : "", value ? "active" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls} style={disabled ? { opacity: .5 } : null}>
      <Ico.search />
      <input value={value} placeholder={placeholder} disabled={disabled} onChange={e => onChange && onChange(e.target.value)} />
      {loading ? <span className="spin"></span>
        : value ? <React.Fragment>
            {resultCount != null && <span className="cbadge">{resultCount}</span>}
            <button className="clr" onClick={onClear}><Ico.clear /></button>
          </React.Fragment>
        : <span className="kbd">⌘K</span>}
    </div>
  );
}

/* ---------- B2 CmdK modal ---------- */
const CMDK_ICON = { memory: Ico.memory, document: Ico.doc, node: Ico.node, agent: Ico.agent };
const CMDK_COLOR = { memory: "var(--accent)", document: "#6e9ecf", node: "var(--grn)", agent: "#c4a86a" };
function CmdK({ query = "", results = [], state = "results", selected = 0 }) {
  return (
    <div className="cmdk-stage">
      <div className="cmdk">
        <div className="cmdk-top"><SearchField value={query} placeholder="Search memories, documents, agents…" loading={state === "loading"} focus /></div>
        {state === "empty"
          ? <div className="cmdk-empty">Type to search across the knowledge base…</div>
          : state === "loading"
            ? <div className="cmdk-list">{[0, 1, 2, 3].map(i => <div className="cmdk-item" key={i}><span className="sk sk-block" style={{ width: 28, height: 28 }}></span><span className="tx"><span className="sk sk-line" style={{ width: "70%", height: 11 }}></span><span className="sk sk-line" style={{ width: "40%", height: 9, marginTop: 6 }}></span></span></div>)}</div>
            : results.length === 0
              ? <div className="cmdk-empty">Nothing found for “{query}”.</div>
              : <div className="cmdk-list">
                  {results.map((r, i) => {
                    const I = CMDK_ICON[r.type] || Ico.memory;
                    return (
                      <div className={"cmdk-item" + (i === selected ? " sel" : "")} key={i}>
                        <span className="ico" style={{ color: CMDK_COLOR[r.type] }}><I /></span>
                        <span className="tx"><span className="tt">{r.title}</span><span className="ss">{r.sub}</span></span>
                        <Chip>{r.kind}</Chip>
                      </div>
                    );
                  })}
                </div>}
        <div className="cmdk-foot"><span><b>↑↓</b> navigate</span><span><b>↵</b> open</span><span><b>esc</b> close</span></div>
      </div>
    </div>
  );
}

/* ---------- B3 Drawer (4 kinds) — rendered inline for the gallery ---------- */
function DwrHead({ kicker, title, desc }) {
  return (
    <div className="dwr-head">
      <div>
        <div className="dwr-kicker"><span className="kdot"></span>{kicker}</div>
        <div className="dwr-title">{title}</div>
        <div className="dwr-desc">{desc}</div>
      </div>
      <button className="dwr-close"><Ico.close /></button>
    </div>
  );
}
function Stat({ v, u, k }) { return <div className="dwr-stat"><div className="v">{v}{u && <span className="u">{u}</span>}</div><div className="k">{k}</div></div>; }
function Li({ lt, x }) { return <div className="dwr-li"><span className="lt">{lt}</span><span>{x}</span></div>; }

function DrawerPanel({ kind, d, state = "open", inline = true }) {
  const body = () => {
    if (state === "loading") return (
      <div className="dwr-body">
        <div className="dwr-stats">{[0, 1, 2, 3].map(i => <div className="dwr-stat" key={i}><span className="sk sk-line" style={{ width: 44, height: 18 }}></span><span className="sk sk-line" style={{ width: 60, height: 9, marginTop: 8 }}></span></div>)}</div>
        <div className="sk sk-block" style={{ height: 80 }}></div>
        <div className="sk sk-block" style={{ height: 120 }}></div>
      </div>
    );
    if (kind === "agent") return (
      <div className="dwr-body">
        <div className="dwr-stats"><Stat v={d.tasksHr} u="/hr" k="throughput" /><Stat v={d.uptime} k="uptime" /><Stat v={d.queue} k="queue depth" /><Stat v={d.errors} u="%" k="error rate" /></div>
        <div className="dwr-sec"><div className="title">Throughput · 1h</div><div className="dwr-chart"><AreaChart data={d.throughput} unit="/min" tipFmt={v => Math.round(v)} /></div></div>
        <div className="dwr-sec"><div className="title">Recent actions</div><div className="dwr-list">{d.actions.map((a, i) => <Li key={i} {...a} />)}</div></div>
        <div className="dwr-btns"><Button variant="primary">Pause agent</Button><Button>View logs</Button></div>
      </div>
    );
    if (kind === "memory") return (
      <div className="dwr-body">
        <div className="dwr-stats"><Stat v={d.salience} k="salience" /><Stat v={d.refs} k="references" /><Stat v={d.cluster} k="cluster" /><Stat v={d.age} k="age" /></div>
        <div className="dwr-sec"><div className="title">Content</div><div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--ink-1)" }}>{d.text}</div></div>
        <div className="dwr-sec"><div className="title">Tags</div><div className="dwr-tags">{d.tags.map(t => <Chip key={t}>{t}</Chip>)}</div></div>
        <div className="dwr-sec"><div className="title">Linked entities</div><div className="dwr-tags">{d.entities.map(t => <Chip key={t}>{t}</Chip>)}</div></div>
        <div className="dwr-btns"><Button variant="primary">Open in Explorer</Button><Button variant="danger">Mark stale</Button></div>
      </div>
    );
    if (kind === "node") return (
      <div className="dwr-body">
        <div className="dwr-stats"><Stat v={d.degree} k="connections" /><Stat v={d.centrality} k="centrality" /><Stat v={d.cluster} k="cluster" /><Stat v={d.updated} k="last edit" /></div>
        <div className="dwr-sec"><div className="title">Linked memories</div><div className="dwr-list">{d.related.map((a, i) => <Li key={i} {...a} />)}</div></div>
        <div className="dwr-sec"><div className="title">Attributes</div><div className="dwr-tags"><Chip>{d.type}</Chip><Chip>degree {d.degree}</Chip><Chip>{d.cluster}</Chip></div></div>
        <div className="dwr-btns"><Button variant="primary">Focus in graph</Button><Button>Pin</Button></div>
      </div>
    );
    /* document */
    return (
      <div className="dwr-body">
        <div className="dwr-stats"><Stat v={d.chunks} k="chunks" /><Stat v={d.size} k="size" /><Stat v={d.indexed} k="indexed" /><Stat v={d.type} k="type" /></div>
        <div className="dwr-sec"><div className="title">Summary</div><div style={{ fontSize: 13.5, lineHeight: 1.6, color: "var(--ink-1)" }}>{d.summary}</div></div>
        <div className="dwr-sec"><div className="title">Recent references</div><div className="dwr-list">{d.refs.map((a, i) => <Li key={i} {...a} />)}</div></div>
        <div className="dwr-btns"><Button variant="primary">Re-index</Button><Button variant="danger">Mark low-trust</Button></div>
      </div>
    );
  };
  const heads = {
    agent: { kicker: "agent · " + (d && d.on ? "online" : "standby"), dotState: d && d.on ? "ok" : "idle", title: d && d.name, desc: d && d.role },
    memory: { kicker: "memory · " + (d && d.type), dotState: "t-" + (d && d.type), title: d && d.short, desc: d && d.meta },
    node: { kicker: "graph node · " + (d && d.type), dotState: "on", title: d && d.label, desc: d && ("Cluster " + d.cluster + " · updated " + d.updated) },
    document: { kicker: "document · " + (d && d.type), dotState: "ok", title: d && d.title, desc: d && d.meta },
  };
  const KIND_COLOR = { memory: "var(--accent)", document: "#6e9ecf", node: "var(--grn)", agent: "#c4a86a" };
  const kindColor = KIND_COLOR[kind] || "var(--accent)";
  return (
    <aside className={"drawer" + (inline ? " inline" : "")} style={{ "--dwrk": kindColor }}>
      <DwrHead {...(heads[kind] || {})} />
      {body()}
    </aside>
  );
}

/* ---------- E1 TopBar ---------- */
function Clock({ t = "14:33:47", d = "Mon, Jun 01" }) {
  return <div className="clockpill"><span className="t">{t}</span><span className="d">{d}</span></div>;
}
function TopBar({ theme = "light", onToggle, accent, search }) {
  return (
    <div className="tray topbar">
      {accent && <div className="statusline" style={{ marginBottom: 10 }}><span className="bar"></span><StatusPill services={6} healthy={6} latency="48ms" /></div>}
      <div className="head" style={{ margin: 0 }}>
        <div className="brand">
          <div className="logo"><b></b></div>
          <div><div className="nm">ecodb<b> · knowledge</b></div><div className="sub">v0.9</div></div>
        </div>
        <SearchField value={search ? search.value : ""} placeholder="Search 1,847 memories, 142 documents…" resultCount={search ? search.count : undefined} onChange={search ? search.onChange : undefined} onClear={search ? search.onClear : undefined} />
        <div className="head-r" style={{ gap: 12 }}>
          {!accent && <StatusPill services={6} healthy={6} latency="48ms" />}
          <Clock />
          <ThemeToggle theme={theme} onToggle={onToggle} />
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { SearchField, CmdK, DrawerPanel, TopBar, Clock });
