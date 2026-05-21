/* =============================================================
   Shared components: Badge, Card, Sparkline, AreaChart, Modal,
   Toast, PageHeader, etc.
   ============================================================= */

const { useState, useEffect, useRef, createContext, useContext, useMemo, useCallback } = React;

/* ---------- Lucide-style inline icons (kept small + no dep) ---------- */
function Icon({ name, size = 14, stroke = 1.6, className = "", style }) {
  const paths = {
    home:         "M3 12 L12 3 L21 12 V20 a1 1 0 0 1-1 1 H4 a1 1 0 0 1-1-1 Z M9 21 V12 H15 V21",
    activity:     "M3 12 H7 L10 4 L14 20 L17 12 H21",
    target:       "M12 12 m-9 0 a9 9 0 1 0 18 0 a9 9 0 1 0-18 0|M12 12 m-5 0 a5 5 0 1 0 10 0 a5 5 0 1 0-10 0|M12 12 m-1 0 a1 1 0 1 0 2 0 a1 1 0 1 0-2 0",
    flask:        "M9 3 H15|M10 3 V10 L4 21 H20 L14 10 V3",
    sparkles:     "M12 3 L13.5 9 L19 10 L13.5 11 L12 17 L10.5 11 L5 10 L10.5 9 Z|M19 4 L19.7 6 L21.7 7 L19.7 8 L19 10 L18.3 8 L16.3 7 L18.3 6 Z|M5 16 L5.7 18 L7.7 19 L5.7 20 L5 22 L4.3 20 L2.3 19 L4.3 18 Z",
    list:         "M8 6 H21|M8 12 H21|M8 18 H21|M3 6 H3.01|M3 12 H3.01|M3 18 H3.01",
    database:     "M12 3 c5 0 9 1.5 9 3 v12 c0 1.5-4 3-9 3 s-9-1.5-9-3 V6 c0-1.5 4-3 9-3 Z|M3 6 c0 1.5 4 3 9 3 s9-1.5 9-3|M3 12 c0 1.5 4 3 9 3 s9-1.5 9-3",
    key:          "M21 2 L13.5 9.5|M16.5 6.5 L18.5 8.5|M11 11 a4 4 0 1 1-4 4 a4 4 0 0 1 4-4 Z",
    download:     "M12 3 V15|M7 10 L12 15 L17 10|M5 21 H19",
    chevronDown:  "M6 9 L12 15 L18 9",
    chevronRight: "M9 6 L15 12 L9 18",
    chevronLeft:  "M15 6 L9 12 L15 18",
    play:         "M6 4 L20 12 L6 20 Z",
    refresh:      "M3 12 a9 9 0 0 1 15-6 L21 9|M21 3 V9 H15|M21 12 a9 9 0 0 1-15 6 L3 15|M3 21 V15 H9",
    clock:        "M12 12 m-9 0 a9 9 0 1 0 18 0 a9 9 0 1 0-18 0|M12 7 V12 L15 14",
    coins:        "M8 9 m-6 0 a6 3 0 1 0 12 0 a6 3 0 1 0-12 0|M2 9 V13 c0 1.66 2.69 3 6 3 s6-1.34 6-3 V9|M16 5 m-6 0 a6 3 0 1 0 12 0 a6 3 0 1 0-12 0|M10 5 V19 c0 1.66 2.69 3 6 3 s6-1.34 6-3 V5",
    alert:        "M12 3 L22 20 H2 Z|M12 9 V14|M12 17 H12.01",
    alertCircle:  "M12 12 m-9 0 a9 9 0 1 0 18 0 a9 9 0 1 0-18 0|M12 8 V12|M12 16 H12.01",
    flag:         "M4 21 V4|M4 4 H17 L15 8 L17 12 H4",
    gitCompare:   "M5 6 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0-6 0|M19 18 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0-6 0|M5 9 V15 a3 3 0 0 0 3 3 H13|M19 15 V9 a3 3 0 0 0-3-3 H11",
    copy:         "M9 9 H20 V20 H9 Z|M5 15 V5 a1 1 0 0 1 1-1 H15",
    search:       "M11 11 m-7 0 a7 7 0 1 0 14 0 a7 7 0 1 0-14 0|M21 21 L17 17",
    bell:         "M6 8 a6 6 0 0 1 12 0 c0 7 3 9 3 9 H3 s3-2 3-9|M10 21 a2 2 0 0 0 4 0",
    x:            "M18 6 L6 18|M6 6 L18 18",
    check:        "M5 13 L9 17 L19 7",
    plus:         "M12 5 V19|M5 12 H19",
    moreH:        "M5 12 m-1 0 a1 1 0 1 0 2 0 a1 1 0 1 0-2 0|M12 12 m-1 0 a1 1 0 1 0 2 0 a1 1 0 1 0-2 0|M19 12 m-1 0 a1 1 0 1 0 2 0 a1 1 0 1 0-2 0",
    filter:       "M3 4 H21 L14 13 V20 L10 18 V13 Z",
    arrowRight:   "M5 12 H19|M13 6 L19 12 L13 18",
    arrowUp:      "M12 19 V5|M6 11 L12 5 L18 11",
    arrowDown:    "M12 5 V19|M6 13 L12 19 L18 13",
    settings:     "M12 12 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0-6 0|M19 12 a7 7 0 0 0-.2-1.7 L21 8.5 L19 5 L16.5 6 a7 7 0 0 0-3-1.7 L13 2 H11 L10.5 4.3 a7 7 0 0 0-3 1.7 L5 5 L3 8.5 L5.2 10.3 a7 7 0 0 0 0 3.4 L3 15.5 L5 19 L7.5 18 a7 7 0 0 0 3 1.7 L11 22 H13 L13.5 19.7 a7 7 0 0 0 3-1.7 L19 19 L21 15.5 L18.8 13.7 a7 7 0 0 0 .2-1.7 Z",
    info:         "M12 12 m-9 0 a9 9 0 1 0 18 0 a9 9 0 1 0-18 0|M12 8 V8.01|M11 12 H12 V16 H13",
    book:         "M2 4 H8 a4 4 0 0 1 4 4 V21 a3 3 0 0 0-3-3 H2 Z|M22 4 H16 a4 4 0 0 0-4 4 V21 a3 3 0 0 1 3-3 H22 Z",
    eye:          "M2 12 s4-7 10-7 s10 7 10 7 s-4 7-10 7 s-10-7-10-7 Z|M12 12 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0-6 0",
    flame:        "M8.5 14.5 A2.5 2.5 0 0 0 11 17 c1 0 2-.5 2.5-1.5 .5 2 1.5 2.5 3.5 2.5 a5 5 0 0 0 5-5 c0-3-3-5-3-9 c-4 0-7 2-7 6 c-3-1-5 1-5 5 Z",
    layers:      "M12 2 L22 8 L12 14 L2 8 Z|M2 16 L12 22 L22 16",
    terminal:    "M4 4 H20 V20 H4 Z|M7 8 L11 12 L7 16|M12 16 H17",
    box:         "M21 8 V18 L12 22 L3 18 V8 L12 4 Z|M3 8 L12 12 L21 8|M12 12 V22",
    grip:        "M6 4 H6.01|M12 4 H12.01|M18 4 H18.01|M6 12 H6.01|M12 12 H12.01|M18 12 H18.01|M6 20 H6.01|M12 20 H12.01|M18 20 H18.01",
    history:    "M3 12 a9 9 0 1 0 3-6.7 L3 8|M3 3 V8 H8|M12 8 V12 L15 14",
  };

  const def = paths[name] || "";
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={stroke}
         strokeLinecap="round" strokeLinejoin="round"
         className={className} style={style} aria-hidden="true">
      {def.split("|").map((d, i) => (
        d.includes("M") || d.includes("L") || d.includes("a") || d.includes("V") || d.includes("H")
          ? <path key={i} d={d} />
          : null
      ))}
    </svg>
  );
}

/* ---------- Badge ---------- */
function Badge({ variant = "default", children }) {
  return (
    <span className={`badge ${variant !== "default" ? `badge--${variant}` : ""}`}>
      <span className="badge__dot" />
      {children}
    </span>
  );
}
function StatusBadge({ status }) {
  const m = { ok: "ok", success: "ok", completed: "ok",
              partial: "warn", queued: "warn", running: "warn",
              error: "err", failed: "err" };
  const label = { ok: "ok", partial: "atenção", error: "erro", running: "rodando", queued: "fila", completed: "ok" }[status] ?? status;
  return <Badge variant={m[status] || "default"}>{label}</Badge>;
}

/* ---------- Preview pill (signals "not real call") ---------- */
function PreviewPill({ label = "preview" }) {
  return <span className="preview-pill"><span className="preview-pill__dot" />{label}</span>;
}

/* ---------- Sparkline ---------- */
function Sparkline({ points, color = "var(--accent)", width = 90, height = 28 }) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points), max = Math.max(...points), range = max - min || 1;
  const step = width / (points.length - 1);
  const d = points.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const fillD = `${d} L ${width} ${height} L 0 ${height} Z`;
  const lastX = (points.length - 1) * step;
  const lastY = height - ((points[points.length - 1] - min) / range) * (height - 4) - 2;
  const gid = useMemo(() => `sg-${Math.random().toString(36).slice(2, 8)}`, []);

  return (
    <svg width={width} height={height} className="metric__spark" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fillD} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r="2.4" fill={color} />
    </svg>
  );
}

/* ---------- Metric card ---------- */
function Metric({ label, icon, value, unit, delta, deltaDir = "neutral", spark, sparkColor }) {
  return (
    <div className="metric">
      <div className="metric__label">{icon ? <Icon name={icon} size={11} /> : null}{label}</div>
      <div className="metric__value">{value}{unit ? <span className="metric__unit">{unit}</span> : null}</div>
      <div className={`metric__delta metric__delta--${deltaDir}`}>
        {deltaDir === "up" ? <Icon name="arrowUp" size={10} /> : deltaDir === "down" ? <Icon name="arrowDown" size={10} /> : null}
        {delta}
      </div>
      {spark ? <Sparkline points={spark} color={sparkColor} /> : null}
    </div>
  );
}

/* ---------- Card ---------- */
function Card({ title, subtitle, action, children, flush }) {
  return (
    <div className="card">
      {(title || action) && (
        <div className="card__header">
          <div>
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <div className="card__subtitle">{subtitle}</div>}
          </div>
          {action && <div className="row">{action}</div>}
        </div>
      )}
      <div className={`card__body${flush ? " card__body--flush" : ""}`}>{children}</div>
    </div>
  );
}

/* ---------- Area chart (cost over time) ---------- */
function AreaChart({ data, color = "var(--accent)", height = 200, valueKey = "cost", labelKey = "label", format = v => v.toFixed(2) }) {
  const ref = useRef(null);
  const [w, setW] = useState(560);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(200, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  const max = Math.max(...data.map(d => d[valueKey]), 0.001);
  const step = data.length > 1 ? w / (data.length - 1) : w;
  const pts = data.map((d, i) => [i * step, height - 28 - (d[valueKey] / max) * (height - 56)]);
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L ${pts[pts.length - 1][0]} ${height - 28} L 0 ${height - 28} Z`;
  const gid = useMemo(() => `area-${Math.random().toString(36).slice(2, 8)}`, []);
  return (
    <div ref={ref} style={{ width: "100%" }}>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" style={{ width: "100%", height }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"  stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map(t => {
          const y = 28 + (height - 56) * t;
          return <line key={t} x1="0" x2={w} y1={y} y2={y} stroke="var(--border-subtle)" strokeDasharray="2 4" />;
        })}
        <path d={area} fill={`url(#${gid})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="1.6" />
        {pts.map((p, i) => i % Math.ceil(pts.length / 7) === 0 ? <circle key={i} cx={p[0]} cy={p[1]} r="2.4" fill={color} /> : null)}
        {data.map((d, i) => i % Math.ceil(data.length / 7) === 0 ? (
          <text key={i} x={i * step} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--text-faint)" fontFamily="var(--font-mono)">{d[labelKey]}</text>
        ) : null)}
      </svg>
    </div>
  );
}

/* ---------- Modal ---------- */
function Modal({ open, onClose, title, subtitle, footer, children, width }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={width ? { width } : null} onClick={e => e.stopPropagation()}>
        <div className="modal__header">
          <div>
            <h3 className="modal__title">{title}</h3>
            {subtitle && <div className="modal__sub">{subtitle}</div>}
          </div>
          <button className="icon-btn" onClick={onClose}><Icon name="x" size={14} /></button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>
  );
}

/* ---------- Endpoint snippet (used in preview modals) ---------- */
function EndpointSnippet({ endpointId }) {
  const ep = window.ENDPOINTS[endpointId];
  if (!ep) return null;
  return (
    <div className="endpoint-snippet">
      <span className={`endpoint-snippet__method method-${ep.method}`}>{ep.method}</span>
      <span>{ep.path}</span>
      <div style={{ marginTop: 8, color: "var(--text-faint)", fontSize: 11.5, fontFamily: "var(--font-sans)" }}>{ep.desc}</div>
    </div>
  );
}

/* ---------- Toast host (event-driven) ---------- */
function ToastHost() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const onToast = (e) => {
      const t = { id: Math.random().toString(36).slice(2, 8), ...e.detail };
      setItems(prev => [...prev, t]);
      setTimeout(() => setItems(prev => prev.filter(x => x.id !== t.id)), 4500);
    };
    window.addEventListener("evo:toast", onToast);
    return () => window.removeEventListener("evo:toast", onToast);
  }, []);
  return (
    <div className="toast-host">
      {items.map(t => (
        <div key={t.id} className="toast">
          <Icon name={t.kind === "ok" ? "check" : t.kind === "err" ? "alertCircle" : "info"} size={15}
                style={{ color: t.kind === "ok" ? "var(--ok)" : t.kind === "err" ? "var(--err)" : "var(--accent)" }} />
          <div style={{ flex: 1 }}>
            <div className="toast__title">{t.title}</div>
            {t.msg && <div className="toast__msg">{t.msg}</div>}
          </div>
          <button className="toast__close" onClick={() => setItems(prev => prev.filter(x => x.id !== t.id))}>
            <Icon name="x" size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
function fireToast(detail) {
  window.dispatchEvent(new CustomEvent("evo:toast", { detail }));
}

/* ---------- Page header ---------- */
function PageHeader({ eyebrow, title, subtitle, badges = [], actions }) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="page-header__eyebrow">{eyebrow}</div>}
        <h1 className="page-header__title">
          {title}
          {badges.map((b, i) => <span key={i}>{b}</span>)}
        </h1>
        {subtitle && <div className="page-header__subtitle">{subtitle}</div>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </div>
  );
}

/* ---------- Score cell ---------- */
function ScoreCell({ value }) {
  if (value === null || value === undefined) return <span className="faint mono">—</span>;
  const tone = value >= 0.85 ? "ok" : value >= 0.7 ? "warn" : "err";
  return (
    <span className={`score score--${tone}`}>
      <span className="score__bar"><i style={{ width: `${value * 100}%` }} /></span>
      {value.toFixed(2)}
    </span>
  );
}

/* ---------- Copyable ---------- */
function Copyable({ value, display }) {
  return (
    <span className="copyable" onClick={(e) => { e.stopPropagation(); navigator.clipboard?.writeText(value); fireToast({ kind: "ok", title: "Copiado", msg: value.slice(0, 40) }); }}>
      <span>{display ?? value}</span>
      <Icon name="copy" size={10} />
    </span>
  );
}

/* ---------- Format helpers ---------- */
const fmt = {
  int: n => new Intl.NumberFormat("pt-BR").format(Math.round(n)),
  num: n => new Intl.NumberFormat("pt-BR", { notation: Math.abs(n) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n),
  money: (n, d = 2) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: d, maximumFractionDigits: d }).format(n),
  ms: ms => ms >= 1000 ? `${(ms/1000).toFixed(2)} s` : `${Math.round(ms)} ms`,
  pct: v => `${(v * 100).toFixed(1)}%`,
};

Object.assign(window, {
  Icon, Badge, StatusBadge, PreviewPill, Sparkline, Metric, Card, AreaChart, Modal,
  EndpointSnippet, ToastHost, fireToast, PageHeader, ScoreCell, Copyable, fmt,
});
