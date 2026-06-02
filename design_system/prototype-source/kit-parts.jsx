/* ECODB KIT — primitives & chrome
   reuses Dot, Toggle, Sparkline, AreaChart, BarChart, Spark, useSize from components.jsx */
const { useState: kS, useEffect: kE, useRef: kR } = React;

/* icons */
const Ico = {
  sun: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M4.5 4.5l1.4 1.4M18.1 18.1l1.4 1.4M3 12h2M19 12h2M4.5 19.5l1.4-1.4M18.1 5.9l1.4-1.4" strokeLinecap="round"/></svg>),
  moon: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M20 14.5A8 8 0 119.5 4a6.3 6.3 0 0010.5 10.5z"/></svg>),
  search: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5" strokeLinecap="round"/></svg>),
  clear: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round"/></svg>),
  close: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 6l12 12M18 6L6 18" strokeLinecap="round"/></svg>),
  memory: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg>),
  doc: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/></svg>),
  node: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="17" cy="18" r="2"/><path d="M8 16.5l8-8M8.5 18h6"/></svg>),
  agent: () => (<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0114 0"/></svg>),
};

function highlight(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return <React.Fragment>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</React.Fragment>;
}

/* ---------- A1 GlassCard ---------- */
function GlassCard({ title, tag, control, accent, variant = "default", state = "rest", hover, msg, children, className = "", style }) {
  const pad = variant === "compact" ? { padding: "12px 14px" } : variant === "flush" ? { padding: 0 } : null;
  const cls = ["card", accent ? "accented" : "", hover ? "is-hover" : "", state === "error" ? "is-error" : "", state === "empty" ? "is-empty" : "", className].filter(Boolean).join(" ");
  const head = (title || tag || control) && (
    <div className="card-head" style={variant === "flush" ? { padding: "14px 16px 10px" } : null}>
      <span className="title" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>{accent && <span className="ca-dot" style={{ background: accent, color: accent }}></span>}{title}</span>{control || (tag && <span className="tag">{tag}</span>)}
    </div>
  );
  return (
    <div className={cls} style={{ ...(accent ? { "--ca": accent } : null), ...pad, ...style }}>
      {head}
      {state === "loading" && <div className="skl-stack" style={variant === "flush" ? { padding: "0 16px 16px" } : null}>
        <div className="sk sk-line" style={{ width: "55%" }}></div>
        <div className="sk sk-block" style={{ height: 56 }}></div>
        <div className="sk sk-line" style={{ width: "38%" }}></div>
      </div>}
      {state === "empty" && <div className="card-msg"><Dot s="idle" /><span className="m">{msg || "no data"}</span></div>}
      {state === "error" && <div className="card-msg"><Dot s="alert" anim="blink" /><span className="m">{msg || "failed to load"}</span><button className="retry">retry ↻</button></div>}
      {(state === "rest" || state === "hover") && children}
    </div>
  );
}

/* ---------- A3 Chip ---------- */
function Chip({ children, tone }) {
  return <span className="chip" style={tone === "hot" ? { color: "var(--accent)" } : null}>{children}</span>;
}

/* ---------- A4 Button ---------- */
function Button({ variant = "default", size, disabled, loading, pressed, children, onClick }) {
  const cls = ["btn", variant !== "default" ? variant : "", size === "sm" ? "sm" : "", disabled ? "is-disabled" : "", pressed ? "is-pressed" : ""].filter(Boolean).join(" ");
  return <button className={cls} disabled={disabled} onClick={onClick}>{loading ? <span className="spin"></span> : children}</button>;
}

/* ---------- A6 SegmentedControl ---------- */
function Segmented({ options, value, onChange }) {
  return <div className="seg">{options.map(o => <button key={o} className={value === o ? "on" : ""} onClick={() => onChange && onChange(o)}>{o}</button>)}</div>;
}

/* ---------- C1 KpiTile ---------- */
function KpiTile({ label, value, unit, series, delta, trend = "up", accent, state = "rest", hover }) {
  if (state === "loading") return (
    <div className="card kpi">
      <div className="sk sk-line" style={{ width: "50%", height: 10 }}></div>
      <div className="sk sk-block" style={{ height: 32, margin: "16px 0" }}></div>
      <div className="sk sk-line" style={{ width: "40%", height: 9 }}></div>
    </div>);
  if (state === "error") return <div className="card kpi is-error"><div className="card-msg"><Dot s="alert" anim="blink" /><span className="m">{label.toLowerCase()} · failed</span><button className="retry">retry ↻</button></div></div>;
  if (state === "empty") return <div className="card kpi is-empty"><div className="kpi-top"><span className="lab">{label}</span><Dot s="idle" /></div><div className="card-msg"><span className="m">no data yet</span></div></div>;
  return (
    <div className={"card kpi" + (hover ? " is-hover" : "")}>
      <div className="kpi-top"><span className="lab">{label}</span><Dot s={trend === "up" ? "ok" : "idle"} /></div>
      <div className="row between"><div className="num">{value}{unit && <span className="u">{unit}</span>}</div><Sparkline data={series} w={84} h={30} accent={accent} /></div>
      <div className="row between"><span className={"delta " + (trend === "up" ? "up" : "dn")}>{trend === "up" ? "↑" : "↓"} {delta}</span><span className="tag">vs last</span></div>
    </div>
  );
}

/* ---------- D1 MemoryRow ---------- */
function MemoryRow({ ts, text, type = "referencia", tags = [], hot, query, onClick }) {
  return (
    <div className={"frow" + (hot ? " hot" : "")} onClick={onClick} style={{ cursor: "pointer" }}>
      <span className="t">{ts}</span>
      <span className="x" style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <Dot s={"t-" + type} />
        <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{highlight(text, query)}</span>
      </span>
      <span className="k">{tags.map(t => <Chip key={t}>{t}</Chip>)}</span>
    </div>
  );
}

/* ---------- D2 AgentRow ---------- */
function AgentRow({ name, role, status = "ok", task, sparkline = [], on, hot, onClick, onToggle }) {
  const sMap = { active: "on", ok: "ok", idle: "idle", error: "alert" };
  const aMap = { active: "blink", ok: "pulse", error: "blink", idle: "" };
  return (
    <div className={"agent" + (hot ? " hot-name" : "")} onClick={onClick} style={{ cursor: "pointer" }}>
      <Dot s={sMap[status]} anim={aMap[status]} />
      <div className="m"><div className="nm">{name}</div><div className="ts">{on ? task : "Standby"}</div></div>
      {on ? <Spark data={sparkline} hot={hot} /> : <span className="ld">idle</span>}
      <span onClick={e => e.stopPropagation()}><Toggle on={on} onChange={onToggle} /></span>
    </div>
  );
}

/* ---------- D3/D4 Attention inbox ---------- */
function InboxItem({ count, label, onClick }) {
  return (
    <div className={"inbox-item" + (count === 0 ? " zero" : "")} onClick={onClick}>
      <Dot s={count > 0 ? "on" : "idle"} anim={count > 0 ? "pulse" : ""} />
      <span className="il">{label}</span>
      <span className={"cbadge2" + (count > 0 ? " hot" : "")}>{count}</span>
    </div>
  );
}
function AttentionInbox({ items, total, state = "rest" }) {
  if (state === "empty" || total === 0) return (
    <GlassCard title="attention inbox" tag="all clear">
      <div className="card-msg"><Dot s="ok" anim="pulse" /><span className="m">nothing needs attention</span></div>
    </GlassCard>
  );
  if (state === "loading") return <GlassCard title="attention inbox" state="loading" />;
  return (
    <GlassCard title="attention inbox" control={<span className="cbadge2 hot">{total}</span>}>
      <div className="inbox">{items.map(it => <InboxItem key={it.label} {...it} />)}</div>
    </GlassCard>
  );
}

/* ---------- E2 StatusPill ---------- */
function StatusPill({ services, healthy, latency }) {
  return (
    <span className="statuspill">
      <Dot s={healthy === services ? "ok" : "alert"} anim={healthy === services ? "pulse" : "blink"} />
      {healthy}/{services} services<span className="sep">·</span><span className="lat">{latency} p95</span>
    </span>
  );
}

/* ---------- E3 ThemeToggle ---------- */
function ThemeToggle({ theme, onToggle }) {
  return <button className="themebtn" onClick={onToggle} aria-label="toggle theme">{theme === "dark" ? <Ico.sun /> : <Ico.moon />}</button>;
}

Object.assign(window, { Ico, highlight, GlassCard, Chip, Button, Segmented, KpiTile, MemoryRow, AgentRow, InboxItem, AttentionInbox, StatusPill, ThemeToggle });
