/* =============================================================
   Evaluations — rubricas em execução, runs, distribuição.
   ============================================================= */

const { useState: useStateEv } = React;

function EvaluationsScreen({ onNav }) {
  const [tab, setTab] = useStateEv("active");
  const [previewAction, setPreviewAction] = useStateEv(null);
  const [drawerId, setDrawerId] = useStateEv(null);

  const totalRuns = window.EVALUATIONS.reduce((s, e) => s + e.runs7d, 0);
  const totalPassRate = (() => {
    let pass = 0, total = 0;
    window.EVALUATIONS.forEach(e => { pass += e.pass * e.runs7d; total += e.runs7d; });
    return total ? pass / total : 0;
  })();

  return (
    <div className="page">
      <PageHeader
        eyebrow="Qualidade"
        title="Avaliações"
        subtitle="LLM-as-judge e heurísticas executadas sobre traces de produção."
        actions={
          <>
            <button className="btn btn--sm" onClick={() => setPreviewAction("triggerEvaluation")}>
              <Icon name="play" size={12} /> Rodar agora
            </button>
            <button className="btn btn--sm" onClick={() => onNav("/rubrics")}>
              <Icon name="list" size={12} /> Ver rubricas
            </button>
            <button className="btn btn--sm btn--primary" onClick={() => setPreviewAction("createRubric")}>
              <Icon name="plus" size={12} /> Nova rubrica
            </button>
          </>
        }
      />

      {/* Summary strip */}
      <section className="kpi-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <Metric label="Rubricas ativas" value={window.RUBRICS.length} delta={`${window.RUBRICS.filter(r => r.type === "llm-judge").length} LLM-judge`} deltaDir="neutral" />
        <Metric label="Runs 7d" value={window.fmt.num(totalRuns)} delta="todas rubricas" deltaDir="neutral" />
        <Metric label="Taxa de aprovação" value={window.fmt.pct(totalPassRate)} delta="média ponderada" deltaDir="up" />
        <Metric label="Custo de avaliação" value={window.fmt.money(0.182, 3)} delta="USD · 7d" deltaDir="neutral" />
      </section>

      {/* Tabs */}
      <nav className="tabs">
        <div className={`tab${tab === "active" ? " is-active" : ""}`} onClick={() => setTab("active")}>
          <Icon name="target" size={11} /> Ativas
          <span className="tab__count">{window.EVALUATIONS.length}</span>
        </div>
        <div className={`tab${tab === "runs" ? " is-active" : ""}`} onClick={() => setTab("runs")}>
          <Icon name="history" size={11} /> Runs recentes
          <span className="tab__count">{window.fmt.int(totalRuns)}</span>
        </div>
        <div className={`tab${tab === "paused" ? " is-active" : ""}`} onClick={() => setTab("paused")}>
          Pausadas
          <span className="tab__count">0</span>
        </div>
      </nav>

      {tab === "active" && (
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Avaliação</th>
                <th>Tipo</th>
                <th>Judge model</th>
                <th className="t__num">Runs 7d</th>
                <th>Score médio</th>
                <th>Distribuição (0 → 1)</th>
                <th>Pass rate</th>
                <th>Última</th>
                <th style={{ width: 32 }}></th>
              </tr>
            </thead>
            <tbody>
              {window.EVALUATIONS.map(ev => {
                const r = window.RUBRICS.find(x => x.id === ev.rubricId);
                return (
                  <tr key={ev.id} onClick={() => setDrawerId(ev.id)}>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span className="t__name">{r.slug}</span>
                        <span className="t__faint" style={{ fontSize: 11 }}>{r.desc}</span>
                      </div>
                    </td>
                    <td>
                      <Badge variant={r.type === "llm-judge" ? "eval" : "info"}>
                        {r.type === "llm-judge" ? "LLM-as-judge" : "Heurística"}
                      </Badge>
                    </td>
                    <td className="t__mono t__muted">{r.model}</td>
                    <td className="t__num">{window.fmt.int(ev.runs7d)}</td>
                    <td>
                      <span className="mono" style={{
                        fontSize: 13,
                        color: ev.avgScore >= 0.85 ? "var(--ok)" : ev.avgScore >= 0.7 ? "var(--warn)" : "var(--err)",
                      }}>{ev.avgScore.toFixed(2)}</span>
                    </td>
                    <td>
                      <div className="distbars">
                        {ev.dist.map((v, i) => {
                          const max = Math.max(...ev.dist);
                          const h = Math.max(2, (v / max) * 22);
                          const c = i < 2 ? "var(--err)" : i < 4 ? "var(--warn)" : "var(--ok)";
                          return <i key={i} style={{ height: h, background: c, opacity: 0.85 }} title={`bucket ${i}: ${v}`} />;
                        })}
                      </div>
                    </td>
                    <td>
                      <span className="mono" style={{
                        fontSize: 12,
                        color: ev.pass >= r.threshold ? "var(--ok)" : "var(--warn)",
                      }}>
                        {window.fmt.pct(ev.pass)}
                      </span>
                      <span className="faint mono" style={{ fontSize: 10, marginLeft: 4 }}>
                        / threshold {window.fmt.pct(r.threshold)}
                      </span>
                    </td>
                    <td className="t__faint" style={{ fontSize: 11 }}>{ev.lastRun} atrás</td>
                    <td><Icon name="chevronRight" size={12} className="t__chev" /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {tab === "runs" && (
        <div className="table-wrap">
          <table className="t">
            <thead>
              <tr>
                <th>Trace</th>
                <th>Rubric</th>
                <th>Status</th>
                <th>Score</th>
                <th className="t__num">Custo</th>
                <th>Quando</th>
              </tr>
            </thead>
            <tbody>
              {window.TRACES.slice(0, 12).map((t, i) => {
                const r = window.RUBRICS[i % window.RUBRICS.length];
                const score = t.score ?? (0.6 + Math.random() * 0.35);
                const passed = score >= r.threshold;
                return (
                  <tr key={t.id} onClick={() => onNav(`/traces/${t.id}`)}>
                    <td><Copyable value={t.id} /></td>
                    <td><span className="t__mono t__muted">{r.slug} v{r.version}</span></td>
                    <td>
                      <Badge variant={passed ? "ok" : "err"}>
                        {passed ? "passou" : "falhou"}
                      </Badge>
                    </td>
                    <td><ScoreCell value={score} /></td>
                    <td className="t__num t__muted">{window.fmt.money(0.0001 + Math.random() * 0.0008, 6)}</td>
                    <td className="t__faint" style={{ fontSize: 11 }}>{t.ago} atrás</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {tab === "paused" && (
        <div className="empty">
          <div className="empty__icon"><Icon name="target" size={18} /></div>
          <div className="empty__title">Nenhuma avaliação pausada</div>
          <div className="empty__desc">Avaliações são pausadas automaticamente quando custo excede o limite ou quando o judge model fica indisponível.</div>
        </div>
      )}

      {drawerId && <EvaluationDrawer evId={drawerId} onClose={() => setDrawerId(null)} setPreviewAction={setPreviewAction} />}
      {previewAction && <PreviewActionModal endpointId={previewAction} onClose={() => setPreviewAction(null)} />}
    </div>
  );
}

function EvaluationDrawer({ evId, onClose, setPreviewAction }) {
  const ev = window.EVALUATIONS.find(e => e.id === evId);
  const r = window.RUBRICS.find(x => x.id === ev.rubricId);
  return (
    <Modal open={true} onClose={onClose}
           title={r.slug}
           subtitle={r.desc}
           width={640}>
      <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)", marginBottom: 0 }}>
        <Metric label="Tipo" value={r.type === "llm-judge" ? "LLM-judge" : "Heurística"} delta={r.model} deltaDir="neutral" />
        <Metric label="Score médio" value={ev.avgScore.toFixed(2)} delta={`threshold ${r.threshold.toFixed(2)}`} deltaDir="neutral" />
        <Metric label="Runs 7d" value={window.fmt.int(ev.runs7d)} delta={`pass ${window.fmt.pct(ev.pass)}`} deltaDir="up" />
      </div>
      <div style={{ marginTop: 16 }}>
        <div className="faint mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>Rubric definition</div>
        <pre className="code">
{`slug: ${r.slug}
version: ${r.version}
type: ${r.type}
model: ${r.model}
threshold: ${r.threshold}
criteria:
  - grounded_in_retrieval
  - cites_specific_chunks
  - follows_response_schema`}
        </pre>
      </div>
      <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn btn--sm" onClick={onClose}>Fechar</button>
        <button className="btn btn--sm" onClick={() => { onClose(); setPreviewAction("publishRubric"); }}>
          <Icon name="arrowUp" size={11} /> Publicar v{r.version + 1}
        </button>
        <button className="btn btn--sm btn--primary" onClick={() => { onClose(); setPreviewAction("triggerEvaluation"); }}>
          <Icon name="play" size={11} /> Rodar
        </button>
      </div>
    </Modal>
  );
}

Object.assign(window, { EvaluationsScreen });
