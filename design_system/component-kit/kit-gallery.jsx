/* ECODB KIT — gallery page */
const { useState: gS } = React;
const seed = (n, f) => Array.from({ length: n }, (_, i) => f(i));
const spk = () => seed(12, () => Math.random());
const ser = (b, a) => seed(20, i => b + Math.sin(i / 3) * a + Math.random() * a * 0.6);

/* ---------- real EcoDB mock data ---------- */
const AGENTS = [
  { name: "Lienzo", role: "Design Lead", status: "active", task: "Building dashboard components", on: true, hot: true, spark: spk() },
  { name: "Hilo", role: "Backend", status: "ok", task: "Resolving graph entity links", on: true, spark: spk() },
  { name: "Prima", role: "Research", status: "ok", task: "Monitoring retrieval drift", on: true, spark: spk() },
  { name: "Eco", role: "Orchestrator", status: "idle", task: "Awaiting review queue", on: false, spark: spk() },
];
const MEMS = [
  { ts: "14:33", text: "Multi-tenant spec aprobado para v0.9", type: "decision", tags: ["ecodb", "multi-tenant"], hot: true },
  { ts: "13:58", text: "Reestructura README v0.9 — arquitectura y contratos", type: "tecnico", tags: ["readme", "v0.9"] },
  { ts: "12:40", text: "GAMR 10 etapas verificado end-to-end", type: "observacion", tags: ["gamr", "workflow-frontend"] },
  { ts: "11:05", text: "Sesión de diseño con Lienzo — kit de componentes", type: "momento", tags: ["design"] },
  { ts: "09:21", text: "Referencia: Apple HIG · Liquid Glass 2025", type: "referencia", tags: ["ref"] },
];
const KPIS = [
  { label: "Memories", value: "1,847", series: ser(1800, 30), delta: "23 today", accent: true },
  { label: "Documents", value: "142", series: ser(130, 6), delta: "4 today" },
  { label: "Graph nodes", value: "1,247", series: ser(1200, 20), delta: "3,291 triples" },
  { label: "Queries / min", value: "297", series: ser(280, 25), delta: "p95 48ms", accent: true },
];
const INBOX = [
  { label: "stale memories", count: 118 },
  { label: "pending alias candidates", count: 18 },
  { label: "unconfirmed relations", count: 0 },
  { label: "low-trust documents", count: 0 },
];
const CMDK_RESULTS = [
  { type: "memory", title: "Multi-tenant spec aprobado para v0.9", sub: "decision · Lienzo · 2h ago", kind: "memory" },
  { type: "document", title: "README v0.9", sub: "document · 142 chunks", kind: "document" },
  { type: "node", title: "Eco Consulting", sub: "graph node · organizacion · degree 14", kind: "node" },
  { type: "agent", title: "Lienzo", sub: "agent · Design Lead · active", kind: "agent" },
  { type: "memory", title: "GAMR 10 etapas verificado", sub: "observacion · 3h ago", kind: "memory" },
];
const D_AGENT = { name: "Lienzo", role: "Design Lead · building the component kit", on: true, tasksHr: 54, uptime: "4d 02h", queue: 7, errors: "0.02", throughput: ser(30, 14), actions: [{ lt: "14:33", x: "Shipped GlassCard + all states" }, { lt: "14:02", x: "Reviewed token contract with frontend" }, { lt: "13:40", x: "Synced kit scope for Phase 1" }] };
const D_MEM = { type: "decision", short: "Multi-tenant spec aprobado", meta: "created 2h ago · Lienzo", salience: "0.92", refs: 7, cluster: "δ-02", age: "2h", text: "Aprobado el spec multi-tenant para EcoDB v0.9: aislamiento por tenant a nivel de namespace, claves de cifrado por organización y cuotas de ingest configurables.", tags: ["ecodb", "multi-tenant", "v0.9"], entities: ["Eco Consulting", "Tenant", "Ingest Quota"] };
const D_NODE = { label: "Eco Consulting", type: "Entity", cluster: "δ-01", degree: 14, centrality: "0.62", updated: "1h ago", related: [{ lt: "14:33", x: "Multi-tenant spec aprobado" }, { lt: "12:40", x: "GAMR 10 etapas verificado" }, { lt: "09:21", x: "Workflow frontend definido" }] };
const D_DOC = { title: "README v0.9", type: "markdown", meta: "indexed 1h ago · 142 chunks", chunks: 142, size: "86 KB", indexed: "1h", summary: "Documentación principal de EcoDB v0.9: arquitectura, contratos de API, modelo de datos y guía de despliegue multi-tenant.", refs: [{ lt: "14:33", x: "Cited by: Multi-tenant spec" }, { lt: "11:05", x: "Updated: deployment section" }] };

/* ---------- helpers ---------- */
function Block({ name, pill, desc, contract, children }) {
  return (
    <section className="block">
      <div className="block-head"><h2>{name}</h2>{pill && <span className="pill">{pill}</span>}</div>
      {desc && <p className="block-desc">{desc}</p>}
      {contract && <code className="contract" dangerouslySetInnerHTML={{ __html: contract }}></code>}
      {children}
    </section>
  );
}
function Pair({ children, one, glass }) {
  const wrap = c => glass ? <div className="card" style={{ padding: "18px 20px", width: "100%" }}>{c}</div> : c;
  return (
    <div className={"pair" + (one ? " one" : "")}>
      <div className="preview" data-theme="light"><span className="theme-tag">light</span>{wrap(children)}</div>
      {!one && <div className="preview" data-theme="dark"><span className="theme-tag">dark</span>{wrap(children)}</div>}
    </div>
  );
}
function St({ label, children, w }) { return <div className={"st" + (w ? " " + w : "")}><div className="st-cap">{label}</div>{children}</div>; }
function Batch({ id, desc }) { return <React.Fragment><div className="kit-batch">{id}</div><div className="kit-batch-desc">{desc}</div></React.Fragment>; }

/* ---------- C5 GraphViewport ---------- */
function GraphViewport({ state = "data", tall }) {
  const h = tall ? 360 : 240;
  let inner;
  if (state === "loading") inner = <div className="screen" style={{ height: h, display: "grid", placeItems: "center", flex: "none" }}><div style={{ display: "flex", gap: 6 }}>{[0, 1, 2].map(i => <span key={i} className="dot ok pulse" style={{ width: 9, height: 9, animationDelay: i * 0.2 + "s" }}></span>)}</div></div>;
  else if (state === "empty") inner = <div className="screen" style={{ height: h, display: "grid", placeItems: "center", flex: "none" }}><span className="mono" style={{ fontSize: 12, color: "var(--node)", opacity: .7 }}>no graph data</span></div>;
  else if (state === "error") inner = <div className="screen" style={{ height: h, display: "grid", placeItems: "center", flex: "none" }}><div className="card-msg"><Dot s="alert" anim="blink" /><span className="m" style={{ color: "var(--node)" }}>graph service unavailable</span></div></div>;
  else inner = <div style={{ height: h, display: "flex", flexDirection: "column" }}><KnowledgeGraph /></div>;
  return (
    <div>
      {inner}
      <div className="gstats" style={{ marginTop: 12 }}>
        <div className="s"><div className="v">96<span className="u">%</span></div><div className="k">connected</div></div>
        <div className="s"><div className="v">3.1</div><div className="k">avg degree</div></div>
        <div className="s"><div className="v">8</div><div className="k">clusters</div></div>
        <div className="s"><div className="v">0.74</div><div className="k">density</div></div>
      </div>
    </div>
  );
}

function App() {
  const [seg, setSeg] = gS("24h");
  const [sv, setSv] = gS("multi-tenant");
  return (
    <div className="kit-wrap">
      <header className="kit-masthead">
        <div className="lede">
          <h1>EcoDB <b>·</b> Component Kit</h1>
          <p>Phase 1 deliverable — every component in isolation, all states, light + dark. Built on the design.md tokens. Compose freely; layout is yours.</p>
        </div>
        <div className="meta"><b>brief</b> phase 1 · kit<br />for <b>Lienzo</b> · design lead<br />tokens <b>design.md §2</b><br />01 jun 2026</div>
      </header>

      <div className="kit-legend">
        <span className="li"><span className="sw" style={{ background: "#F5631E" }}></span>accent · live/active/critical</span>
        <span className="li"><span className="sw" style={{ background: "#4E9E6A" }}></span>ok</span>
        <span className="li"><span className="sw" style={{ background: "#DE4630" }}></span>alert</span>
        <span className="li"><span className="sw" style={{ background: "#6e9ecf" }}></span>tecnico</span>
        <span className="li"><span className="sw" style={{ background: "#c4a86a" }}></span>observacion</span>
        <span className="li mono">DM Mono · data &nbsp;|&nbsp; Hanken Grotesk · copy</span>
      </div>

      {/* ===================== BATCH A ===================== */}
      <Batch id="Batch A — Containers & primitives" desc="Everything else sits inside these." />

      <Block name="A1 · GlassCard" pill="container" desc="The raised, frosted container. Cursor-tracked specular on hover. Variants: default / compact / flush. States: rest, hover, loading, empty, error."
        contract={`<span class="k">GlassCard</span>{ title?, tag?, control?, variant: 'default'|'compact'|'flush', state: 'rest'|'hover'|'loading'|'empty'|'error' }`}>
        <Pair>
          <div className="states">
            <St label="rest" w="w-card"><GlassCard title="repository" tag="core"><div className="mono" style={{ fontSize: 26, color: "var(--ink-1)" }}>1,847</div><div className="tag" style={{ marginTop: 6 }}>memories</div></GlassCard></St>
            <St label="hover" w="w-card"><GlassCard title="repository" tag="core" hover><div className="mono" style={{ fontSize: 26, color: "var(--ink-1)" }}>1,847</div><div className="tag" style={{ marginTop: 6 }}>memories</div></GlassCard></St>
            <St label="loading" w="w-card"><GlassCard title="repository" tag="core" state="loading" /></St>
            <St label="empty" w="w-card"><GlassCard title="repository" tag="core" state="empty" msg="no memories yet" /></St>
            <St label="error" w="w-card"><GlassCard title="repository" tag="core" state="error" msg="failed to load" /></St>
          </div>
        </Pair>
      </Block>

      <Block name="A2 · Dot" pill="indicator" desc="The one inset element (recessed well). on-accent / ok / alert / idle, with pulse / blink / none."
        contract={`<span class="k">Dot</span>{ s: 'on'|'ok'|'alert'|'idle', anim?: 'pulse'|'blink' }`}>
        <Pair glass>
          <div className="states">
            <St label="on · pulse"><div className="st-row"><Dot s="on" anim="pulse" /></div></St>
            <St label="ok"><div className="st-row"><Dot s="ok" /></div></St>
            <St label="alert · blink"><div className="st-row"><Dot s="alert" anim="blink" /></div></St>
            <St label="idle"><div className="st-row"><Dot s="idle" /></div></St>
            <St label="large"><div className="st-row"><span className="dot on pulse" style={{ width: 14, height: 14 }}></span></div></St>
          </div>
        </Pair>
      </Block>

      <Block name="A3 · Chip" pill="label" desc="Mono micro-label for tags, types, roles."
        contract={`<span class="k">Chip</span>{ children, tone?: 'hot' }`}>
        <Pair glass>
          <div className="states"><St label="default"><div className="st-row"><Chip>ecodb</Chip><Chip>v0.9</Chip><Chip>multi-tenant</Chip></div></St><St label="hot"><div className="st-row"><Chip tone="hot">decision</Chip></div></St></div>
        </Pair>
      </Block>

      <Block name="A4 · Button" pill="action" desc="Compact only. default / primary / danger, plus pressed, loading, disabled."
        contract={`<span class="k">Button</span>{ variant: 'default'|'primary'|'danger', loading?, disabled?, pressed? }`}>
        <Pair glass>
          <div className="states">
            <St label="default"><div className="st-row"><Button>View logs</Button></div></St>
            <St label="primary · solid"><div className="st-row"><Button variant="primary">Open in Explorer</Button></div></St>
            <St label="primary · tint"><div className="st-row"><Button variant="tint">Open in Explorer</Button></div></St>
            <St label="danger"><div className="st-row"><Button variant="danger">Mark stale</Button></div></St>
            <St label="loading"><div className="st-row"><Button variant="primary" loading /></div></St>
            <St label="disabled"><div className="st-row"><Button disabled>Disabled</Button></div></St>
          </div>
        </Pair>
      </Block>

      <Block name="A5 · Toggle" pill="control" desc="Neutral graphite track when on — never orange."
        contract={`<span class="k">Toggle</span>{ on: boolean, onChange }`}>
        <Pair glass>
          <div className="states"><St label="off"><div className="st-row"><Toggle on={false} /></div></St><St label="on"><div className="st-row"><Toggle on={true} /></div></St></div>
        </Pair>
      </Block>

      <Block name="A6 · SegmentedControl" pill="control" desc="Smooth active fill. e.g. time ranges."
        contract={`<span class="k">Segmented</span>{ options: string[], value, onChange }`}>
        <Pair glass>
          <div className="states"><St label="interactive"><div className="st-row"><Segmented options={["1h", "24h", "7d"]} value={seg} onChange={setSeg} /></div></St></div>
        </Pair>
      </Block>

      {/* ===================== BATCH B ===================== */}
      <Batch id="Batch B — Search & navigation" desc="The most-used interactions. SearchField is the hero." />

      <Block name="B1 · SearchField" pill="hero" desc="Generous height. empty / typing / focused / loading / has-results / disabled. ⌘K badge when idle."
        contract={`<span class="k">SearchField</span>{ value, placeholder, resultCount?, loading?, focus?, disabled?, onChange, onClear }`}>
        <Pair>
          <div className="states" style={{ flexDirection: "column", width: "100%" }}>
            <St label="idle" w="w-wide"><SearchField placeholder="Search 1,847 memories, 142 documents…" /></St>
            <St label="focused" w="w-wide"><SearchField placeholder="Search…" focus /></St>
            <St label="typing · results" w="w-wide"><SearchField value="multi-tenant" resultCount={6} /></St>
            <St label="loading" w="w-wide"><SearchField value="reindex" loading /></St>
            <St label="disabled" w="w-wide"><SearchField placeholder="Search…" disabled /></St>
          </div>
        </Pair>
      </Block>

      <Block name="B2 · CmdK Modal" pill="overlay" desc="⌘K palette. Glass backdrop + heavy blur. results / empty / no-results / loading. ↑↓ select, ↵ open, esc close."
        contract={`<span class="k">CmdK</span>{ query, results: {type,title,sub,kind}[], state: 'results'|'empty'|'loading', selected }`}>
        <Pair>
          <div className="states" style={{ flexDirection: "column", width: "100%" }}>
            <St label="results" w="w-wide"><CmdK query="multi" results={CMDK_RESULTS} selected={0} /></St>
            <St label="no results" w="w-wide"><CmdK query="zzz" results={[]} /></St>
            <St label="loading" w="w-wide"><CmdK query="multi" state="loading" /></St>
          </div>
        </Pair>
      </Block>

      <Block name="B3 · Drawer" pill="overlay" desc="Right-side glass panel (shown inline here). kind: agent / memory / node / document — header + body + footer change per kind. Closes on ✕ / scrim / esc."
        contract={`<span class="k">Drawer</span>{ kind: 'agent'|'memory'|'node'|'document', d, state: 'open'|'loading' }`}>
        <Pair>
          <div className="states">
            <St label="kind · agent"><DrawerPanel kind="agent" d={D_AGENT} /></St>
            <St label="kind · node"><DrawerPanel kind="node" d={D_NODE} /></St>
          </div>
        </Pair>
        <Pair>
          <div className="states">
            <St label="kind · memory"><DrawerPanel kind="memory" d={D_MEM} /></St>
            <St label="kind · document"><DrawerPanel kind="document" d={D_DOC} /></St>
            <St label="loading"><DrawerPanel kind="agent" d={D_AGENT} state="loading" /></St>
          </div>
        </Pair>
      </Block>

      {/* ===================== BATCH C ===================== */}
      <Batch id="Batch C — Data display" desc="What the user reads." />

      <Block name="C1 · KpiTile" pill="metric" desc="Label, big value, sparkline, delta. accent ⇒ orange sparkline. rest / hover / loading / empty / error."
        contract={`<span class="k">KpiTile</span>{ label, value, unit?, series: number[], delta, trend: 'up'|'down', accent? }`}>
        <Pair>
          <div className="states">
            <St label="accent" w="w-kpi"><KpiTile {...KPIS[0]} trend="up" /></St>
            <St label="default" w="w-kpi"><KpiTile {...KPIS[1]} trend="up" /></St>
            <St label="hover" w="w-kpi"><KpiTile {...KPIS[2]} trend="up" hover /></St>
            <St label="loading" w="w-kpi"><KpiTile label="Memories" state="loading" /></St>
            <St label="error" w="w-kpi"><KpiTile label="Latency" state="error" /></St>
          </div>
        </Pair>
      </Block>

      <Block name="C2 · AreaChart" pill="time-series" desc="Smooth Catmull-Rom, gradient fill, grid, 'now' marker, hover crosshair + tooltip, optional target band. Hover over it."
        contract={`<span class="k">AreaChart</span>{ data: number[], min?, max?, band?: [lo,hi], unit, tipFmt? }`}>
        <Pair>
          <div className="states" style={{ flexDirection: "column", width: "100%" }}>
            <St label="data · target band" w="w-wide"><div style={{ height: 130, display: "flex", flexDirection: "column" }}><AreaChart data={ser(94, 3)} min={84} max={99} band={[94, 96]} unit="%" tipFmt={v => v.toFixed(1)} /></div></St>
            <St label="empty" w="w-wide"><GlassCard variant="flush" state="empty" msg="no data for this period" style={{ height: 90 }} /></St>
          </div>
        </Pair>
      </Block>

      <Block name="C3 · BarChart" pill="distribution" desc="Most recent bar = orange. Hover for exact value."
        contract={`<span class="k">BarChart</span>{ data: number[] }`}>
        <Pair>
          <div className="states" style={{ width: "100%" }}><St label="data" w="w-wide"><div style={{ height: 110, display: "flex", flexDirection: "column" }}><BarChart data={seed(16, () => 30 + Math.random() * 60)} /></div></St></div>
        </Pair>
      </Block>

      <Block name="C4 · Sparkline" pill="inline" desc="Tiny, axis-less. Embeds in KpiTile + AgentRow. accent ⇒ orange."
        contract={`<span class="k">Sparkline</span>{ data: number[], accent? }`}>
        <Pair glass>
          <div className="states"><St label="graphite"><div className="st-row"><Sparkline data={spk()} w={120} h={30} /></div></St><St label="accent"><div className="st-row"><Sparkline data={spk()} w={120} h={30} accent /></div></St></div>
        </Pair>
      </Block>

      <Block name="C5 · GraphViewport" pill="canvas" desc="The one dark inset screen (both themes). Animated constellation, traveling pulses, hover labels, one hot node. Stats bar below. data / loading / empty / error."
        contract={`<span class="k">GraphViewport</span>{ state: 'data'|'loading'|'empty'|'error', onPick(nodeId), tall? }`}>
        <Pair>
          <div className="states" style={{ width: "100%" }}><St label="data · hover & click nodes" w="w-wide"><GraphViewport state="data" /></St></div>
        </Pair>
        <Pair>
          <div className="states"><St label="loading"><div style={{ width: 260 }}><GraphViewport state="loading" /></div></St><St label="error"><div style={{ width: 260 }}><GraphViewport state="error" /></div></St></div>
        </Pair>
      </Block>

      {/* ===================== BATCH D ===================== */}
      <Batch id="Batch D — Lists & rows" desc="The content the user scans. Click any row → Drawer." />

      <Block name="D1 · MemoryRow" pill="row" desc="Timestamp · type dot · text (search-highlightable) · tags. hot ⇒ orange accent line. Type colors: decision / tecnico / momento / observacion / referencia."
        contract={`<span class="k">MemoryRow</span>{ ts, text, type, tags: string[], hot?, query? }`}>
        <Pair>
          <GlassCard title="recent memories" tag="live capture" variant="flush">
            <div style={{ padding: "0 16px 12px" }}>{MEMS.map((m, i) => <MemoryRow key={i} {...m} query={sv} />)}</div>
          </GlassCard>
        </Pair>
      </Block>

      <Block name="D2 · AgentRow" pill="row" desc="Status dot · name · task · sparkline · toggle. Active agent ⇒ orange name."
        contract={`<span class="k">AgentRow</span>{ name, role, status: 'active'|'ok'|'idle'|'error', task?, sparkline: number[], on, hot? }`}>
        <Pair>
          <GlassCard title="active agents" tag="3/4 online" variant="flush">
            <div style={{ padding: "0 16px 10px" }}>{AGENTS.map((a, i) => <AgentRow key={i} {...a} sparkline={a.spark} hot={a.status === "active"} on={a.on} />)}</div>
          </GlassCard>
        </Pair>
      </Block>

      <Block name="D3/D4 · Attention Inbox" pill="checklist" desc="Decision-class checklist with counts. count>0 ⇒ orange dot + hot badge. count 0 ⇒ idle. all-clear is a GOOD empty state."
        contract={`<span class="k">AttentionInbox</span>{ items: {label,count}[], total, state? }   <span class="c">// item → InboxItem</span>`}>
        <Pair>
          <div className="states">
            <St label="data" w="w-card"><AttentionInbox items={INBOX} total={136} /></St>
            <St label="all clear" w="w-card"><AttentionInbox items={[]} total={0} /></St>
          </div>
        </Pair>
      </Block>

      {/* ===================== BATCH E ===================== */}
      <Batch id="Batch E — Chrome & system" desc="Topbar, status, theme. Glass tray (not a card)." />

      <Block name="E1 · TopBar" pill="tray" desc="Logo + version · SearchField · StatusPill + Clock + ThemeToggle. Optional thin orange status accent line — shown both ways."
        contract={`<span class="k">TopBar</span>{ theme, onToggle, accent?, search }`}>
        <Pair one>
          <div className="states" style={{ width: "100%", gap: 16 }}>
            <St label="default" w="w-wide"><TopBar theme="light" search={{ value: sv, count: 6, onChange: setSv, onClear: () => setSv("") }} /></St>
            <St label="with orange status accent" w="w-wide"><TopBar theme="light" accent search={{ value: "", onChange: setSv, onClear: () => setSv("") }} /></St>
          </div>
        </Pair>
        <Pair one>
          <div className="preview" data-theme="dark" style={{ padding: 26 }}><span className="theme-tag">dark</span>
            <div className="states" style={{ width: "100%", gap: 16 }}>
              <St label="default" w="w-wide"><TopBar theme="dark" accent search={{ value: "", onChange: () => {}, onClear: () => {} }} /></St>
            </div>
          </div>
        </Pair>
      </Block>

      <Block name="E2 · StatusPill" pill="system" desc="Services healthy + p95 latency. Lives in TopBar."
        contract={`<span class="k">StatusPill</span>{ services, healthy, latency }`}>
        <Pair glass>
          <div className="states"><St label="healthy"><div className="st-row"><StatusPill services={6} healthy={6} latency="48ms" /></div></St><St label="degraded"><div className="st-row"><StatusPill services={6} healthy={5} latency="210ms" /></div></St></div>
        </Pair>
      </Block>

      <Block name="E3 · ThemeToggle" pill="control" desc="Recessed flat button. Sun (in dark) / moon (in light)."
        contract={`<span class="k">ThemeToggle</span>{ theme, onToggle }`}>
        <Pair glass>
          <div className="states"><St label="on light"><div className="st-row"><ThemeToggle theme="light" /></div></St><St label="on dark"><div className="st-row"><ThemeToggle theme="dark" /></div></St></div>
        </Pair>
      </Block>

      <footer style={{ marginTop: 70, paddingTop: 24, borderTop: "1px solid rgba(40,38,34,.1)", fontFamily: "var(--font-mono)", fontSize: 11, color: "#9a948a" }}>
        EcoDB Component Kit · Phase 1 · {KPIS.length + AGENTS.length} live demos · built on design.md tokens · for review by Lienzo
      </footer>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
