/* ECODB — dashboard components (Liquid Glass) */
const { useState, useEffect, useRef, useId } = React;

function useSize(ref) {
  const [s, setS] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const measure = () => { if (!ref.current) return; const r = ref.current.getBoundingClientRect(); setS({ w: r.width, h: r.height }); };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return s;
}

function smoothPath(p) {
  if (p.length < 2) return "";
  let d = `M ${p[0][0].toFixed(1)} ${p[0][1].toFixed(1)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] || p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6, c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6, c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d;
}

/* ====================================================================
   Area chart — line + gradient fill + grid, orange last point
   ==================================================================== */
function AreaChart({ data, min, max, pad = 8, grid = 3, band, unit = "", tipFmt }) {
  const ref = useRef(null); const { w, h } = useSize(ref);
  const id = useId().replace(/:/g, "");
  const [hov, setHov] = useState(null);
  const lo = min != null ? min : Math.min(...data);
  const hi = max != null ? max : Math.max(...data);
  const range = (hi - lo) || 1;
  const n = data.length;
  const X = i => (i / (n - 1)) * w;
  const Y = v => pad + (1 - (v - lo) / range) * (h - 2 * pad);
  const pts = data.map((v, i) => [X(i), Y(v)]);
  const line = smoothPath(pts);
  const area = line + ` L ${w.toFixed(1)} ${h} L 0 ${h} Z`;
  const last = pts[n - 1] || [0, 0];
  const gridLines = [];
  for (let i = 1; i <= grid; i++) gridLines.push(pad + (i / (grid + 1)) * (h - 2 * pad));

  const onMove = e => {
    const r = ref.current.getBoundingClientRect();
    let idx = Math.round((e.clientX - r.left) / r.width * (n - 1));
    setHov(Math.max(0, Math.min(n - 1, idx)));
  };
  const hp = hov != null ? pts[hov] : null;

  return (
    <div className="chart-wrap" ref={ref} onPointerMove={onMove} onPointerLeave={() => setHov(null)}>
      {w > 0 && (
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          <defs>
            <linearGradient id={"ag" + id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-fill-1)" />
              <stop offset="100%" stopColor="var(--chart-fill-2)" />
            </linearGradient>
          </defs>
          {gridLines.map((y, i) => <line key={i} x1="0" y1={y} x2={w} y2={y} stroke="var(--chart-grid)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
          {band && <rect x="0" y={Y(band[1])} width={w} height={Math.max(0, Y(band[0]) - Y(band[1]))} fill="var(--accent)" opacity="0.06" />}
          <path d={area} fill={`url(#ag${id})`} />
          <path d={line} fill="none" stroke="var(--chart-line)" strokeWidth="1.75" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
          {!hp && <line x1={last[0]} y1={last[1]} x2={last[0]} y2={h} stroke="var(--accent)" strokeWidth="1" strokeDasharray="2 3" vectorEffect="non-scaling-stroke" opacity="0.5" />}
          {!hp && <circle cx={last[0]} cy={last[1]} r="3.4" fill="var(--accent)" stroke="var(--card-bg)" strokeWidth="1.5" style={{ filter: "drop-shadow(0 0 4px rgba(245,99,30,.6))" }} />}
          {hp && <line x1={hp[0]} y1="0" x2={hp[0]} y2={h} stroke="var(--accent)" strokeWidth="1" vectorEffect="non-scaling-stroke" opacity="0.6" />}
          {hp && <circle cx={hp[0]} cy={hp[1]} r="3.6" fill="var(--accent)" stroke="var(--card-bg)" strokeWidth="1.5" />}
        </svg>
      )}
      {hp && <div className="tip" style={{ left: hp[0], top: hp[1] }}>{tipFmt ? tipFmt(data[hov]) : data[hov].toFixed(1)}<span className="tu">{unit}</span></div>}
    </div>
  );
}

/* ====================================================================
   Bar chart — vertical bars, last accent
   ==================================================================== */
function BarChart({ data, pad = 6 }) {
  const ref = useRef(null); const { w, h } = useSize(ref);
  const hi = Math.max(...data, 1);
  const n = data.length;
  const gap = 3;
  const bw = (w - gap * (n - 1)) / n;
  return (
    <div className="chart-wrap" ref={ref}>
      {w > 0 && (
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
          {data.map((v, i) => {
            const bh = Math.max(2, (v / hi) * (h - pad));
            const x = i * (bw + gap);
            return <rect key={i} x={x} y={h - bh} width={bw} height={bh} rx="1.5"
              fill={i === n - 1 ? "var(--accent)" : "var(--chart-bar)"} />;
          })}
        </svg>
      )}
    </div>
  );
}

/* ====================================================================
   Sparkline — tiny line for KPIs
   ==================================================================== */
function Sparkline({ data, w = 96, h = 30, accent }) {
  const lo = Math.min(...data), hi = Math.max(...data), range = (hi - lo) || 1;
  const n = data.length;
  const pts = data.map((v, i) => [(i / (n - 1)) * w, 4 + (1 - (v - lo) / range) * (h - 8)]);
  const line = smoothPath(pts);
  const last = pts[n - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
      <path d={line} fill="none" stroke={accent ? "var(--accent)" : "var(--ink-3)"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity={accent ? 1 : 0.7} />
      <circle cx={last[0]} cy={last[1]} r="2.2" fill="var(--accent)" />
    </svg>
  );
}

/* ==================================================================== */
function Dot({ s = "idle", anim }) { return <span className={`dot ${s} ${anim || ""}`}></span>; }
function Toggle({ on, onChange }) { return <button className={`tgl ${on ? "on" : ""}`} onClick={() => onChange && onChange(!on)} aria-pressed={on}><span className="kn"></span></button>; }
function Spark({ data, h = 16, hot }) {
  const max = Math.max(...data, 1);
  return <div className="spark" style={{ height: h }}>
    {data.map((v, i) => <i key={i} className={hot && i === data.length - 1 ? "hot" : ""} style={{ height: Math.max(2, (v / max) * h) }}></i>)}
  </div>;
}

Object.assign(window, { AreaChart, BarChart, Sparkline, Dot, Toggle, Spark, useSize });
