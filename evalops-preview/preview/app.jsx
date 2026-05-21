/* =============================================================
   EvalOps Preview — App entry. Wires shell + router + screens.
   ============================================================= */

const { useState: useStateApp, useEffect: useEffectApp } = React;

function App() {
  const [route, go] = window.useRoute();

  // keyboard shortcuts (G + key)
  useEffectApp(() => {
    let last = 0;
    const onKey = (e) => {
      if (e.target.matches("input, textarea, select")) return;
      const now = Date.now();
      if (e.key === "g" || e.key === "G") { last = now; return; }
      if (now - last < 900) {
        const map = { o: "/", t: "/traces", e: "/evaluations", x: "/experiments",
                      p: "/prompts", r: "/rubrics", d: "/datasets",
                      k: "/keys" };
        const k = e.key.toLowerCase();
        if (map[k]) { go(map[k]); last = 0; }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  // route → screen
  let screen;
  if (route === "/" || route === "") {
    screen = <window.OverviewScreen onNav={go} />;
  } else if (route === "/traces") {
    screen = <window.TracesScreen onNav={go} />;
  } else if (route.startsWith("/traces/")) {
    const id = route.replace("/traces/", "");
    screen = <window.TraceDetailScreen traceId={id} onNav={go} />;
  } else if (route === "/evaluations") {
    screen = <window.EvaluationsScreen onNav={go} />;
  } else if (["/prompts","/rubrics","/datasets","/experiments","/keys","/exports"].includes(route)) {
    const id = route.replace("/", "");
    screen = <window.ModuleScreen moduleId={id} onNav={go} />;
  } else {
    screen = <NotFound onNav={go} />;
  }

  return (
    <div className="app-shell">
      <window.Sidebar current={route} onNav={go} />
      <main style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <window.Topbar current={route} onNav={go} />
        {screen}
      </main>
      <window.ToastHost />
    </div>
  );
}

function NotFound({ onNav }) {
  return (
    <div className="page">
      <div className="empty" style={{ marginTop: 80 }}>
        <div className="empty__icon"><window.Icon name="search" size={18} /></div>
        <div className="empty__title">Tela não encontrada</div>
        <div className="empty__desc">A rota acessada não existe neste preview. Volte para o overview ou use a navegação à esquerda.</div>
        <button className="btn btn--sm btn--primary" onClick={() => onNav("/")}>
          Ir para Visão geral
        </button>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
