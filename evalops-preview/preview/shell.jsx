/* =============================================================
   App shell: Sidebar, Topbar, Router (hash-based navigation).
   ============================================================= */

const { useState: useStateShell, useEffect: useEffectShell, useMemo: useMemoShell } = React;

const ROUTES = [
  { section: "Projeto", items: [
    { id: "overview",    label: "Visão geral", icon: "home",     path: "/",            shortcut: "G O" },
    { id: "traces",      label: "Traces",      icon: "activity", path: "/traces",      shortcut: "G T", count: window.TRACES.length },
    { id: "evaluations", label: "Avaliações",  icon: "target",   path: "/evaluations", shortcut: "G E" },
    { id: "experiments", label: "Experimentos",icon: "flask",    path: "/experiments", shortcut: "G X" },
  ]},
  { section: "Recursos", items: [
    { id: "prompts",     label: "Prompts",     icon: "sparkles", path: "/prompts" },
    { id: "rubrics",     label: "Rubricas",    icon: "list",     path: "/rubrics" },
    { id: "datasets",    label: "Datasets",    icon: "database", path: "/datasets" },
  ]},
  { section: "Operação", items: [
    { id: "keys",        label: "Chaves API",  icon: "key",      path: "/keys",     dot: true },
    { id: "exports",     label: "Exports",     icon: "download", path: "/exports" },
  ]},
];

function useRoute() {
  const [hash, setHash] = useStateShell(() => window.location.hash.replace(/^#/, "") || "/");
  useEffectShell(() => {
    const onHash = () => setHash(window.location.hash.replace(/^#/, "") || "/");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const go = (path) => { window.location.hash = path; };
  return [hash, go];
}

function Sidebar({ current, onNav }) {
  const ws = window.WORKSPACE;
  return (
    <aside className="sidebar">
      <div className="sb-brand">
        <div className="sb-brand__logo" aria-hidden="true">
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
            <path d="M2 3.5 L7 1 L12 3.5 L12 10.5 L7 13 L2 10.5 Z" stroke="white" strokeWidth="1.4" />
            <circle cx="7" cy="7" r="1.7" fill="white" />
          </svg>
        </div>
        <div className="sb-brand__name">EvalOps</div>
        <span className="sb-brand__ver">v0.7</span>
      </div>

      <div className="sb-workspace" onClick={() => window.fireToast({ kind: "info", title: "Troca de workspace", msg: "Seletor de org/projeto — preview" })}>
        <div className="sb-workspace__avatar">{ws.org.slice(0, 2).toUpperCase()}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="sb-workspace__org">{ws.org} · prod</div>
          <div className="sb-workspace__proj">{ws.projectName}</div>
        </div>
        <Icon name="chevronDown" size={12} className="sb-workspace__chev" />
      </div>

      {ROUTES.map(({ section, items }) => (
        <div className="sb-section" key={section}>
          <div className="sb-section__label">{section}</div>
          {items.map(item => {
            const active = current === item.path || (item.path !== "/" && current.startsWith(item.path));
            return (
              <div key={item.id}
                   className={`sb-nav-item${active ? " is-active" : ""}`}
                   onClick={() => onNav(item.path)}>
                <Icon name={item.icon} size={14} />
                <span>{item.label}</span>
                {item.count != null && <span className="sb-nav-item__count">{window.fmt.int(item.count)}</span>}
                {item.dot && <span className="sb-nav-item__dot" title="Atenção" />}
                {item.shortcut && item.count == null && !item.dot &&
                  <span className="sb-nav-item__shortcut">{item.shortcut}</span>}
              </div>
            );
          })}
        </div>
      ))}

      <div className="sb-footer">
        <div className="sb-status">
          <span className="sb-status__pulse" aria-hidden="true" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="sb-status__name">SDK Python</div>
            <div className="sb-status__meta">{ws.sdkVersion}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

/* ---------- Topbar ---------- */
function Topbar({ current, onNav }) {
  const ws = window.WORKSPACE;
  const [notifOpen, setNotifOpen] = useStateShell(false);
  const [searchOpen, setSearchOpen] = useStateShell(false);
  const trail = useMemoShell(() => crumbsForRoute(current), [current]);

  return (
    <header className="topbar">
      <div className="crumbs">
        <span>{ws.org}</span>
        <span className="crumbs__sep">/</span>
        <span>{ws.project}</span>
        {trail.map((c, i) => (
          <React.Fragment key={i}>
            <span className="crumbs__sep">/</span>
            {c.path ? <span style={{ cursor: "pointer" }} onClick={() => onNav(c.path)}>{c.label}</span> : <strong>{c.label}</strong>}
          </React.Fragment>
        ))}
      </div>

      <div className="topbar__search">
        <Icon name="search" size={13} className="topbar__search-icon" />
        <input placeholder="Buscar traces, prompts, rubricas…"
               onFocus={() => setSearchOpen(true)}
               onBlur={() => setTimeout(() => setSearchOpen(false), 150)} />
        <span className="topbar__search-kbd">⌘K</span>
      </div>

      <div className="topbar__right">
        <span className="env-chip"><span className="env-chip__dot" />env: {ws.environment}</span>

        <div style={{ position: "relative" }}>
          <button className="icon-btn" onClick={() => setNotifOpen(o => !o)} title="Notificações">
            <Icon name="bell" size={14} />
            <span className="icon-btn__badge" />
          </button>
          {notifOpen && (
            <div style={{
              position: "absolute", right: 0, top: 36, width: 320,
              background: "var(--surface-1)", border: "1px solid var(--border)",
              borderRadius: "var(--r-md)", boxShadow: "0 12px 32px -8px oklch(0 0 0 / 0.6)",
              zIndex: 50,
            }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid var(--border-subtle)", fontSize: 12, fontWeight: 600 }}>
                Notificações
              </div>
              {window.NOTIFICATIONS.map(n => (
                <div key={n.id} className="row-section" style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <Icon name={n.kind === "warn" || n.kind === "err" ? "alertCircle" : "info"} size={14}
                        style={{ color: n.kind === "err" ? "var(--err)" : n.kind === "warn" ? "var(--warn)" : "var(--accent)", marginTop: 1 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, color: "var(--text)" }}>{n.title}</div>
                    <div style={{ fontSize: 10.5, color: "var(--text-faint)", fontFamily: "var(--font-mono)", marginTop: 2 }}>{n.meta}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <button className="icon-btn" onClick={() => window.fireToast({ kind: "info", title: "Configurações", msg: "Settings — fora do redesign inicial" })}>
          <Icon name="settings" size={14} />
        </button>

        <div className="user-avatar" title="Rouger X.">RX</div>
      </div>
    </header>
  );
}

function crumbsForRoute(route) {
  if (route === "/" || route === "") return [{ label: "Visão geral" }];
  if (route === "/traces") return [{ label: "Traces" }];
  if (route.startsWith("/traces/")) return [{ label: "Traces", path: "/traces" }, { label: route.split("/").pop() }];
  const labels = {
    "/evaluations": "Avaliações", "/experiments": "Experimentos",
    "/prompts": "Prompts", "/rubrics": "Rubricas", "/datasets": "Datasets",
    "/keys": "Chaves API", "/exports": "Exports",
  };
  return [{ label: labels[route] || route }];
}

Object.assign(window, { Sidebar, Topbar, useRoute, ROUTES });
