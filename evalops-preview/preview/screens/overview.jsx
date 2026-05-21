/* =============================================================
   Overview / Visão geral — cockpit central
   ============================================================= */

const { useState: useStateOv, useMemo: useMemoOv } = React;

function OverviewScreen({ onNav }) {
  const [window_, setWindow_] = useStateOv("7d");
  const [previewAction, setPreviewAction] = useStateOv(null);

  const kpis = window.KPIS;
  const cost = window.COST_BY_DAY;
  const traces = window.TRACES;
  const flagged = traces.filter(t => t.status !== "ok").slice(0, 4);

  const totalCalls = window.MODEL_BREAKDOWN.reduce((s, m) => s + m.calls, 0);

  return (
    <div className="page">
      <PageHeader
        eyebrow={`Workspace · ${window.WORKSPACE.org}`}
        title={window.WORKSPACE.projectName}
        subtitle={`Resumo de operação · janela: últimos ${window_ === "24h" ? "24 horas" : window_ === "7d" ? "7 dias" : "30 dias"} · env: prod`}
        actions={
          <>
            <select className="filter-select" value={window_} onChange={e => setWindow_(e.target.value)}>
              <option value="24h">Últimas 24h</option>
              <option value="7d">Últimos 7 dias</option>
              <option value="30d">Últimos 30 dias</option>
            </select>
            <button className="btn btn--sm" onClick={() => window.fireToast({ kind: "ok", title: "Overview atualizado", msg: "GET /v1/projects/{id}/overview" })}>
              <Icon name="refresh" size={12} /> Atualizar
            </button>
            <button className="btn btn--sm btn--primary" onClick={() => setPreviewAction("triggerEvaluation")}>
              <Icon name="play" size={12} /> Rodar avaliação
            </button>
          </>
        }
      />

      {/* Attention strip */}
      {flagged.length > 0 && (
        <div className="attention">
          <div className="attention__icon"><Icon name="alert" size={14} /></div>
          <div>
            <div className="attention__title">{flagged.length} traces precisam de atenção nas últimas 24h</div>
            <div className="attention__desc">
              Schema mismatch, timeouts e baixa confiança em respostas RAG. Concentre-se nesta lista antes do próximo deploy.
            </div>
          </div>
          <button className="btn btn--sm" onClick={() => onNav("/traces")}>
            Revisar traces <Icon name="arrowRight" size={11} />
          </button>
        </div>
      )}

      {/* KPIs */}
      <section className="kpi-grid kpi-grid--5">
        <Metric label="Traces" icon="activity"
                value={window.fmt.num(kpis.traces.value)}
                delta={kpis.traces.delta} deltaDir={kpis.traces.dir}
                spark={kpis.traces.spark} />
        <Metric label="p95 latência" icon="clock"
                value={(kpis.latencyP95.value / 1000).toFixed(2)} unit="s"
                delta={kpis.latencyP95.delta} deltaDir="down"
                spark={kpis.latencyP95.spark} sparkColor="var(--warn)" />
        <Metric label="Custo" icon="coins"
                value={window.fmt.money(kpis.cost.value)}
                delta={kpis.cost.delta} deltaDir={kpis.cost.dir}
                spark={kpis.cost.spark} sparkColor="var(--eval)" />
        <Metric label="Taxa de erro" icon="alertCircle"
                value={window.fmt.pct(kpis.errorRate.value)}
                delta={kpis.errorRate.delta} deltaDir="up"
                spark={kpis.errorRate.spark} sparkColor="var(--err)" />
        <Metric label="Score médio" icon="target"
                value={kpis.avgScore.value.toFixed(2)}
                delta={kpis.avgScore.delta} deltaDir="up"
                spark={kpis.avgScore.spark} sparkColor="var(--ok)" />
      </section>

      {/* Chart + model breakdown */}
      <section className="grid-2" style={{ marginBottom: 12 }}>
        <Card title="Custo & volume por dia" subtitle="USD · últimos 14 dias"
              action={<>
                <Badge variant="info">cost</Badge>
                <button className="btn btn--ghost btn--sm btn--icon" title="Exportar"
                        onClick={() => setPreviewAction("exportTraces")}>
                  <Icon name="download" size={12} />
                </button>
              </>}>
          <AreaChart data={cost} valueKey="cost" labelKey="label" />
        </Card>

        <Card title="Custo por modelo"
              action={<button className="btn btn--ghost btn--sm" onClick={() => onNav("/traces")}>
                Ver detalhes <Icon name="arrowRight" size={11} />
              </button>} flush>
          <table className="t">
            <thead>
              <tr><th>Modelo</th><th className="t__num">Calls</th><th className="t__num">Custo</th><th>Share</th></tr>
            </thead>
            <tbody>
              {window.MODEL_BREAKDOWN.map(m => {
                const share = m.calls / totalCalls;
                return (
                  <tr key={m.model} onClick={() => onNav("/traces")}>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                        <span className="t__name">{m.model}</span>
                        <span className="t__faint mono" style={{ fontSize: 10 }}>{m.provider}</span>
                      </div>
                    </td>
                    <td className="t__num t__muted">{window.fmt.int(m.calls)}</td>
                    <td className="t__num">{window.fmt.money(m.cost, 4)}</td>
                    <td>
                      <span className="share">
                        <span className="share__bar"><i style={{ width: `${share * 100}%` }} /></span>
                        <span className="share__pct">{Math.round(share * 100)}%</span>
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </section>

      {/* Problem traces */}
      <Card title="Últimos traces com problema"
            subtitle="status diferente de ok · ordenado por mais recente"
            action={<button className="btn btn--sm" onClick={() => onNav("/traces")}>
              Ver todos os traces <Icon name="arrowRight" size={11} />
            </button>} flush>
        <table className="t">
          <thead>
            <tr>
              <th>Trace</th><th>ID</th><th>Status</th><th>Causa</th>
              <th className="t__num">Duração</th><th className="t__num">Custo</th>
              <th>Modelo</th><th>Quando</th><th style={{ width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {flagged.length === 0 ? (
              <tr><td colSpan={9} className="t__empty">Nenhum trace com problema nesta janela 🎉</td></tr>
            ) : flagged.map(t => (
              <tr key={t.id} className="is-flagged" onClick={() => onNav(`/traces/${t.id}`)}>
                <td>
                  <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                    <span className="t__name">{t.name}</span>
                    <span className="t__faint mono" style={{ fontSize: 10 }}>{t.service}{t.isRag ? " · RAG" : ""}</span>
                  </div>
                </td>
                <td><Copyable value={t.id} /></td>
                <td><StatusBadge status={t.status} /></td>
                <td>{t.flagged ? <span className="tag" style={{ color: "var(--err)", borderColor: "oklch(0.72 0.18 22 / 0.3)" }}>{t.flagged}</span> : <span className="faint">—</span>}</td>
                <td className="t__num t__muted">{window.fmt.ms(t.duration)}</td>
                <td className="t__num">{window.fmt.money(t.cost, 5)}</td>
                <td className="t__mono">{t.model}</td>
                <td className="t__faint" style={{ fontSize: 11 }}>{t.ago}</td>
                <td><Icon name="chevronRight" size={12} className="t__chev" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div style={{ height: 12 }} />

      {/* Bottom row — operational shortcuts */}
      <section className="grid-3">
        <Card title="Saúde do SDK" subtitle="ingestão · últimos 60min">
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <div className="row" style={{ marginBottom: 8 }}>
                <span className="badge badge--ok"><span className="badge__dot" />ingestão ok</span>
                <span className="faint mono" style={{ fontSize: 10 }}>p95 18ms</span>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Recebendo eventos do <span className="mono">aurora-rag</span> e <span className="mono">billing-agent</span>.
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="mono" style={{ fontSize: 18, color: "var(--text)" }}>1,842</div>
              <div className="faint mono" style={{ fontSize: 10 }}>spans/min</div>
            </div>
          </div>
        </Card>

        <Card title="Próximos passos sugeridos">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <SuggestionRow icon="play" title="Rodar answer-grounding-v2"
                           desc="1.320 traces RAG sem score nesta janela"
                           onClick={() => setPreviewAction("triggerEvaluation")} />
            <SuggestionRow icon="gitCompare" title="Comparar refund-system v5 vs v6"
                           desc="experimento já configurado em refund-golden-set"
                           onClick={() => setPreviewAction("createExperiment")} />
            <SuggestionRow icon="download" title="Exportar erros 7d para fine-tune"
                           desc="62 traces com status=error"
                           onClick={() => setPreviewAction("exportTraces")} />
          </div>
        </Card>

        <Card title="Cobertura por avaliação" subtitle="% de traces com pelo menos uma run">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {window.EVALUATIONS.slice(0, 4).map(ev => {
              const r = window.RUBRICS.find(x => x.id === ev.rubricId);
              const coverage = Math.min(1, ev.runs7d / 4500);
              return (
                <div key={ev.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="mono" style={{ fontSize: 12 }}>{r.slug}</span>
                    <span className="mono faint" style={{ fontSize: 11 }}>{Math.round(coverage * 100)}%</span>
                  </div>
                  <div className="share__bar" style={{ width: "100%" }}>
                    <i style={{ width: `${coverage * 100}%`, background: coverage >= 0.7 ? "var(--ok)" : coverage >= 0.4 ? "var(--warn)" : "var(--err)" }} />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <footer className="app-footer">
        <span>© 2026 EvalOps Studio · preview interno</span>
        <span className="spacer" />
        <a href="#" onClick={(e) => { e.preventDefault(); window.fireToast({ kind: "info", title: "Docs", msg: "Abriria /docs no app real" }); }}>Documentação</a>
        <a href="#" onClick={(e) => { e.preventDefault(); window.fireToast({ kind: "info", title: "Status", msg: "GET /health/readiness" }); }}>Status</a>
        <span className="row" style={{ gap: 5, color: "var(--ok)" }}>
          <Icon name="check" size={11} /> Sistemas operando
        </span>
      </footer>

      {previewAction && (
        <PreviewActionModal
          endpointId={previewAction}
          onClose={() => setPreviewAction(null)}
        />
      )}
    </div>
  );
}

function SuggestionRow({ icon, title, desc, onClick }) {
  return (
    <div className="row" style={{
      gap: 10, padding: "8px 10px", border: "1px solid var(--border-subtle)",
      borderRadius: "var(--r-sm)", background: "var(--surface-2)",
      cursor: "pointer",
    }} onClick={onClick}>
      <div style={{
        width: 28, height: 28, borderRadius: "var(--r-sm)",
        background: "var(--accent-soft)", border: "1px solid var(--accent-rim)",
        display: "grid", placeItems: "center", color: "var(--accent)",
        flexShrink: 0,
      }}>
        <Icon name={icon} size={12} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, color: "var(--text)", fontWeight: 500 }}>{title}</div>
        <div style={{ fontSize: 11, color: "var(--text-faint)" }}>{desc}</div>
      </div>
      <Icon name="arrowRight" size={11} style={{ color: "var(--text-faint)" }} />
    </div>
  );
}

function PreviewActionModal({ endpointId, onClose }) {
  const titles = {
    triggerEvaluation: "Rodar avaliação",
    exportTraces: "Exportar traces",
    createExperiment: "Criar experimento A/B",
    rerunTrace: "Reexecutar trace",
    compareTraces: "Comparar traces",
    flagTrace: "Flagear trace",
    createKey: "Criar API key",
    revokeKey: "Revogar API key",
    createPrompt: "Criar nova versão de prompt",
    createDataset: "Criar dataset",
    createRubric: "Criar rubrica",
    publishRubric: "Publicar rubrica",
    createExport: "Criar export JSONL",
    downloadExport: "Baixar export",
  };
  return (
    <Modal open={true} onClose={onClose}
           title={titles[endpointId] || "Ação"}
           subtitle="Este preview não tem backend conectado. A ação real chamaria o endpoint abaixo.">
      <EndpointSnippet endpointId={endpointId} />
      <div style={{ marginTop: 8, padding: "10px 12px", background: "var(--surface-2)", border: "1px dashed var(--border)", borderRadius: 6, fontSize: 12, color: "var(--text-muted)" }}>
        <strong style={{ color: "var(--text)" }}>Status:</strong> ação real preservada para implementação. Nada será persistido neste preview.
      </div>
      <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button className="btn btn--sm" onClick={onClose}>Fechar</button>
        <button className="btn btn--sm btn--primary" onClick={() => { window.fireToast({ kind: "ok", title: "Ação simulada", msg: "Preview: nenhuma chamada real foi feita." }); onClose(); }}>
          Simular sucesso
        </button>
      </div>
    </Modal>
  );
}

Object.assign(window, { OverviewScreen, PreviewActionModal });
