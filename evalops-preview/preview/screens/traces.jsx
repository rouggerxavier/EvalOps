/* =============================================================
   Traces list — filtros, tabs, tabela densa.
   ============================================================= */

const { useState: useStateTr, useMemo: useMemoTr } = React;

function TracesScreen({ onNav }) {
  const [tab, setTab] = useStateTr("all");
  const [statusF, setStatusF] = useStateTr("all");
  const [envF, setEnvF] = useStateTr("all");
  const [nameQ, setNameQ] = useStateTr("");
  const [previewAction, setPreviewAction] = useStateTr(null);

  const filtered = useMemoTr(() => {
    let rows = window.TRACES;
    if (tab === "errors") rows = rows.filter(t => t.status === "error");
    if (tab === "partial") rows = rows.filter(t => t.status === "partial");
    if (tab === "slow") rows = rows.filter(t => t.duration > 2000);
    if (tab === "rag") rows = rows.filter(t => t.isRag);
    if (statusF !== "all") rows = rows.filter(t => t.status === statusF);
    if (envF !== "all") rows = rows.filter(t => t.env === envF);
    if (nameQ) rows = rows.filter(t => t.name.toLowerCase().includes(nameQ.toLowerCase()));
    return rows;
  }, [tab, statusF, envF, nameQ]);

  const counts = {
    all: window.TRACES.length,
    errors: window.TRACES.filter(t => t.status === "error").length,
    partial: window.TRACES.filter(t => t.status === "partial").length,
    slow: window.TRACES.filter(t => t.duration > 2000).length,
    rag: window.TRACES.filter(t => t.isRag).length,
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Observabilidade"
        title="Traces"
        subtitle={`${window.fmt.int(window.TRACES.length)} traces no intervalo atual · auto-refresh a cada 30s`}
        actions={
          <>
            <span className="env-chip" style={{ marginRight: 4 }}><span className="env-chip__dot" />ao vivo</span>
            <button className="btn btn--sm" onClick={() => setPreviewAction("exportTraces")}>
              <Icon name="download" size={12} /> Exportar JSONL
            </button>
            <button className="btn btn--sm" onClick={() => window.fireToast({ kind: "info", title: "Auto-refresh ativo", msg: "30s · sem cursor" })}>
              <Icon name="refresh" size={12} /> Refresh
            </button>
          </>
        }
      />

      <nav className="tabs">
        {[
          { id: "all", label: "Todos", icon: null },
          { id: "errors", label: "Erros", icon: "alertCircle" },
          { id: "partial", label: "Parciais", icon: "flag" },
          { id: "slow", label: "Lentos", icon: "clock" },
          { id: "rag", label: "RAG", icon: "layers" },
        ].map(t => (
          <div key={t.id}
               className={`tab${tab === t.id ? " is-active" : ""}`}
               onClick={() => setTab(t.id)}>
            {t.icon && <Icon name={t.icon} size={11} />} {t.label}
            <span className="tab__count">{counts[t.id]}</span>
          </div>
        ))}
      </nav>

      <div className="filters">
        <div className="filter-group">
          <Icon name="search" size={12} />
          <input className="filter-input" placeholder="buscar por nome (ex: refund, chat.answer)"
                 value={nameQ} onChange={e => setNameQ(e.target.value)} />
        </div>
        <select className="filter-select" value={statusF} onChange={e => setStatusF(e.target.value)}>
          <option value="all">qualquer status</option>
          <option value="ok">ok</option>
          <option value="partial">parcial</option>
          <option value="error">erro</option>
        </select>
        <select className="filter-select" value={envF} onChange={e => setEnvF(e.target.value)}>
          <option value="all">qualquer env</option>
          <option value="prod">prod</option>
          <option value="staging">staging</option>
        </select>
        <span className="spacer" />
        <span className="faint mono" style={{ fontSize: 11 }}>
          {filtered.length} de {window.TRACES.length}
        </span>
      </div>

      <div className="table-wrap">
        {filtered.length === 0 ? (
          <div className="empty" style={{ border: "none", borderRadius: 0 }}>
            <div className="empty__icon"><Icon name="activity" size={18} /></div>
            <div className="empty__title">Nenhum trace encontrado</div>
            <div className="empty__desc">Ajuste os filtros ou conecte o SDK para começar a capturar tráfego de produção.</div>
            <div className="empty__code">{`import evalops
evalops.init(api_key="evk_prod_...", project="aurora-support", environment="prod")

@evalops.trace("chat.answer")
def answer(msg: str): ...`}</div>
          </div>
        ) : (
          <table className="t">
            <thead>
              <tr>
                <th style={{ width: 28 }}>
                  <input type="checkbox" disabled style={{ opacity: 0.4, accentColor: "var(--accent)" }} title="Seleção em lote — planejado" />
                </th>
                <th>Nome</th>
                <th>Trace ID</th>
                <th>Status</th>
                <th>Env</th>
                <th>Modelo</th>
                <th className="t__num">Duração</th>
                <th className="t__num">Tokens</th>
                <th className="t__num">Custo</th>
                <th>Score</th>
                <th>Quando</th>
                <th style={{ width: 28 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(t => (
                <tr key={t.id}
                    className={t.status !== "ok" ? "is-flagged" : ""}
                    onClick={() => onNav(`/traces/${t.id}`)}>
                  <td onClick={e => e.stopPropagation()}>
                    <input type="checkbox" disabled style={{ opacity: 0.4, accentColor: "var(--accent)" }} title="planejado" />
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      <span className="t__name">{t.name}</span>
                      <span className="t__faint mono" style={{ fontSize: 10 }}>
                        {t.service}{t.isRag ? <> · <span style={{ color: "oklch(0.74 0.14 195)" }}>RAG</span></> : null}
                      </span>
                    </div>
                  </td>
                  <td onClick={e => e.stopPropagation()}><Copyable value={t.id} display={t.id} /></td>
                  <td><StatusBadge status={t.status} /></td>
                  <td><span className="tag">{t.env}</span></td>
                  <td className="t__mono">{t.model}</td>
                  <td className="t__num" style={{
                    color: t.duration > 4000 ? "var(--err)" : t.duration > 2000 ? "var(--warn)" : "var(--text-dim)",
                  }}>{window.fmt.ms(t.duration)}</td>
                  <td className="t__num t__muted">
                    {window.fmt.int(t.tokensIn)}<span className="faint">/{window.fmt.int(t.tokensOut)}</span>
                  </td>
                  <td className="t__num">{window.fmt.money(t.cost, 5)}</td>
                  <td>{t.score != null ? <ScoreCell value={t.score} /> : <span className="faint mono">—</span>}</td>
                  <td className="t__faint" style={{ fontSize: 11 }}>{t.ago} atrás</td>
                  <td><Icon name="chevronRight" size={12} className="t__chev" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12, fontSize: 11.5, color: "var(--text-muted)" }}>
        <span>Mostrando {filtered.length} traces</span>
        <div className="row">
          <button className="btn btn--sm btn--ghost" disabled><Icon name="chevronLeft" size={12} /></button>
          <button className="btn btn--sm btn--ghost" onClick={() => window.fireToast({ kind: "info", title: "Paginação", msg: "GET /v1/traces?cursor=…" })}>
            <Icon name="chevronRight" size={12} />
          </button>
        </div>
      </div>

      {previewAction && <PreviewActionModal endpointId={previewAction} onClose={() => setPreviewAction(null)} />}
    </div>
  );
}

/* =============================================================
   Trace detail
   ============================================================= */

function TraceDetailScreen({ traceId, onNav }) {
  const trace = window.TRACES.find(t => t.id === traceId) || window.TRACES[0];
  const detail = window.TRACE_DETAIL[trace.id] || window.TRACE_DETAIL["trc_8f4a92d1"];
  const [previewAction, setPreviewAction] = useStateTr(null);
  const [tab, setTab] = useStateTr(trace.isRag ? "rag" : "waterfall");
  const [fbThumbs, setFbThumbs] = useStateTr("up");
  const [fbComment, setFbComment] = useStateTr("");

  return (
    <div className="page">
      <PageHeader
        eyebrow={<span style={{ cursor: "pointer", color: "var(--accent)" }} onClick={() => onNav("/traces")}>← Traces</span>}
        title={<span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="mono" style={{ fontSize: 17, color: "var(--text)", fontWeight: 500, letterSpacing: "-0.01em" }}>{trace.name}</span>
          <StatusBadge status={trace.status} />
          <span className="tag">{trace.env}</span>
          {trace.isRag && <Badge variant="rag">RAG</Badge>}
        </span>}
        subtitle={<span className="row" style={{ gap: 10, fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
          <Copyable value={trace.id} />
          <span>·</span>
          <span>{trace.service}</span>
          <span>·</span>
          <span>{trace.ago} atrás</span>
          {detail.metadata && <><span>·</span><span>user: {detail.metadata["user.ref"]}</span></>}
        </span>}
        actions={
          <>
            <button className="btn btn--sm" onClick={() => setPreviewAction("flagTrace")}>
              <Icon name="flag" size={12} /> Flagear
            </button>
            <button className="btn btn--sm" onClick={() => setPreviewAction("rerunTrace")}>
              <Icon name="play" size={12} /> Reexecutar
            </button>
            <button className="btn btn--sm" onClick={() => setPreviewAction("compareTraces")}>
              <Icon name="gitCompare" size={12} /> Comparar
            </button>
            <button className="btn btn--sm btn--primary" onClick={() => setPreviewAction("triggerEvaluation")}>
              <Icon name="target" size={12} /> Avaliar
            </button>
          </>
        }
      />

      {/* Error banner if this trace failed */}
      {detail.error && (
        <div className="attention" style={{
          background: "oklch(0.72 0.18 22 / 0.06)",
          borderColor: "oklch(0.72 0.18 22 / 0.4)",
          marginBottom: 16,
        }}>
          <div className="attention__icon"><Icon name="alertCircle" size={14} /></div>
          <div>
            <div className="attention__title">{detail.error.type}</div>
            <div className="attention__desc"><span className="mono">{detail.error.message}</span> · em <span className="mono">{detail.error.at}</span></div>
          </div>
          <button className="btn btn--sm" onClick={() => setPreviewAction("rerunTrace")}>Reexecutar</button>
        </div>
      )}

      {/* KPIs */}
      <section className="kpi-grid kpi-grid--5">
        <Metric label="Duração" value={window.fmt.ms(trace.duration)} delta={`p95: ${(trace.duration * 1.2 / 1000).toFixed(2)}s no name`} deltaDir="neutral" />
        <Metric label="Tokens entrada" value={window.fmt.int(trace.tokensIn)} delta="prompt" deltaDir="neutral" />
        <Metric label="Tokens saída" value={window.fmt.int(trace.tokensOut)} delta="completion" deltaDir="neutral" />
        <Metric label="Custo" value={window.fmt.money(trace.cost, 5)} delta={trace.model} deltaDir="neutral" />
        <Metric label="Spans / Eventos" value={`${detail.spans.length}`} unit={`/ ${detail.spans.length * 4}`} delta="capturados" deltaDir="neutral" />
      </section>

      {/* Tabs */}
      <nav className="tabs">
        {trace.isRag && (
          <div className={`tab${tab === "rag" ? " is-active" : ""}`} onClick={() => setTab("rag")}>
            <Icon name="layers" size={11} /> RAG
          </div>
        )}
        <div className={`tab${tab === "waterfall" ? " is-active" : ""}`} onClick={() => setTab("waterfall")}>
          <Icon name="activity" size={11} /> Waterfall
          <span className="tab__count">{detail.spans.length}</span>
        </div>
        <div className={`tab${tab === "metadata" ? " is-active" : ""}`} onClick={() => setTab("metadata")}>
          <Icon name="terminal" size={11} /> Metadata
        </div>
        <div className={`tab${tab === "feedback" ? " is-active" : ""}`} onClick={() => setTab("feedback")}>
          <Icon name="flag" size={11} /> Feedback
          <span className="tab__count">{detail.feedback?.length || 0}</span>
        </div>
      </nav>

      {/* RAG tab */}
      {tab === "rag" && trace.isRag && (
        <RagPanel detail={detail} />
      )}

      {/* Waterfall */}
      {tab === "waterfall" && (
        <Card title="Waterfall" subtitle={`${detail.spans.length} spans · escala absoluta`} flush>
          <div className="waterfall__scale">
            <span></span><span></span>
            <div className="waterfall__scale-line">
              {[0, 0.25, 0.5, 0.75, 1].map(t => (
                <span key={t}>{Math.round(trace.duration * t)}ms</span>
              ))}
            </div>
            <span></span>
          </div>
          <div className="waterfall">
            {detail.spans.map(sp => {
              const left = (sp.offset / trace.duration) * 100;
              const width = Math.max(1, (sp.duration / trace.duration) * 100);
              return (
                <div key={sp.id} className="waterfall__row">
                  <div className="waterfall__name">
                    <span className="waterfall__kind">{sp.kind}</span>
                    {sp.name}
                  </div>
                  <div className="t__num t__faint" style={{ fontSize: 10 }}>{sp.offset}ms</div>
                  <div className="waterfall__bar">
                    <i className={`k-${sp.kind}`} style={{ left: `${left}%`, width: `${width}%` }} />
                  </div>
                  <div className="waterfall__duration">{window.fmt.ms(sp.duration)}</div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Metadata */}
      {tab === "metadata" && (
        <div className="grid-detail">
          <Card title="Metadata do trace" subtitle="JSON raw · armazenado em traces.metadata"
                action={<button className="btn btn--sm btn--ghost" onClick={() => { navigator.clipboard?.writeText(JSON.stringify(detail.metadata, null, 2)); window.fireToast({ kind: "ok", title: "JSON copiado" }); }}>
                  <Icon name="copy" size={12} /> Copiar JSON
                </button>}>
            <pre className="code">{JSON.stringify(detail.metadata, null, 2)}</pre>
          </Card>
          <Card title="Ações reais" subtitle="endpoints que esta tela usa">
            <div className="endpoint-list">
              {["getTrace", "createFeedback", "flagTrace", "rerunTrace", "compareTraces"].map(id => {
                const ep = window.ENDPOINTS[id];
                return (
                  <div className="endpoint-row" key={id}>
                    <span className={`endpoint-snippet__method method-${ep.method}`}>{ep.method}</span>
                    <span className="endpoint-row__path" title={ep.path}>{ep.path.replace(/^\/v1/, "")}</span>
                    <span className="endpoint-row__note">{["rerunTrace", "compareTraces"].includes(id) ? "planejado" : "ativo"}</span>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {/* Feedback */}
      {tab === "feedback" && (
        <div className="grid-detail">
          <Card title="Histórico de feedback" subtitle={`${detail.feedback?.length || 0} entradas`} flush>
            {detail.feedback?.length ? detail.feedback.map(fb => (
              <div key={fb.id} className="row-section">
                <div className="row" style={{ justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 13 }}>{fb.thumbs === "up" ? "👍" : "👎"} <span className="mono faint" style={{ fontSize: 11 }}>{fb.who}</span></span>
                  <span className="faint mono" style={{ fontSize: 10 }}>{fb.at}</span>
                </div>
                {fb.comment && <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>{fb.comment}</p>}
              </div>
            )) : (
              <div className="t__empty">Nenhum feedback humano registrado ainda.</div>
            )}
          </Card>
          <Card title="Registrar feedback" subtitle="POST /v1/traces/{id}/feedback">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <label style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>Avaliação</label>
                <div className="row" style={{ marginTop: 6 }}>
                  <button className={`btn btn--sm ${fbThumbs === "up" ? "btn--primary" : ""}`} onClick={() => setFbThumbs("up")}>👍 Positivo</button>
                  <button className={`btn btn--sm ${fbThumbs === "down" ? "btn--primary" : ""}`} onClick={() => setFbThumbs("down")}>👎 Negativo</button>
                </div>
              </div>
              <div>
                <label style={{ fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.08em", fontFamily: "var(--font-mono)" }}>Comentário</label>
                <input className="filter-input" style={{ marginTop: 6, width: "100%", padding: "0 10px", minWidth: 0 }}
                       value={fbComment} onChange={e => setFbComment(e.target.value)}
                       placeholder="O que aconteceu neste trace?" />
              </div>
              <button className="btn btn--primary" onClick={() => { setPreviewAction("createFeedback"); }}>
                <Icon name="check" size={12} /> Enviar feedback
              </button>
            </div>
          </Card>
        </div>
      )}

      {previewAction && <PreviewActionModal endpointId={previewAction} onClose={() => setPreviewAction(null)} />}
    </div>
  );
}

/* ---------- RAG panel ---------- */
function RagPanel({ detail }) {
  const r = detail.rag;
  const riskColor = r.hallucinationRisk === "low" ? "var(--ok)" : r.hallucinationRisk === "medium" ? "var(--warn)" : "var(--err)";
  return (
    <>
      <div className="rag-header">
        <div className="rag-header__title">
          <div style={{ width: 24, height: 24, borderRadius: 5, background: "oklch(0.7 0.14 195 / 0.18)", border: "1px solid oklch(0.7 0.14 195 / 0.4)", display: "grid", placeItems: "center", color: "oklch(0.74 0.14 195)" }}>
            <Icon name="layers" size={12} />
          </div>
          <strong>Trace RAG</strong>
        </div>
        <div>
          <div className="rag-stat__label">Docs recuperados</div>
          <div className="rag-stat__value">{r.retrievedDocs}</div>
        </div>
        <div>
          <div className="rag-stat__label">Score médio</div>
          <div className="rag-stat__value" style={{ color: r.avgScore >= 0.8 ? "var(--ok)" : r.avgScore >= 0.6 ? "var(--warn)" : "var(--err)" }}>{r.avgScore.toFixed(2)}</div>
        </div>
        <div>
          <div className="rag-stat__label">Claims grounded</div>
          <div className="rag-stat__value"><span style={{ color: "var(--ok)" }}>{r.groundedClaims}</span><span className="faint"> / {r.groundedClaims + r.ungroundedClaims}</span></div>
        </div>
        <div>
          <div className="rag-stat__label">Risco</div>
          <div className="rag-stat__value" style={{ color: riskColor, textTransform: "capitalize" }}>{r.hallucinationRisk}</div>
        </div>
        <PreviewPill label="rag heurístico" />
      </div>

      <div className="grid-2-eq" style={{ marginBottom: 12 }}>
        <Card title="Resposta gerada" subtitle="answer preview · primeiros 400 chars">
          <div style={{
            background: "var(--bg-1)", border: "1px solid var(--border-subtle)",
            borderRadius: "var(--r-sm)", padding: 14,
            fontSize: 13, lineHeight: 1.6, color: "var(--text-dim)",
          }}>
            {r.answerPreview}
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <span className="tag">refund_request</span>
            <span className="tag">7-day window</span>
            <span className="tag" style={{ color: "var(--warn)", borderColor: "oklch(0.82 0.14 80 / 0.3)" }}>reembolso parcial: não coberto</span>
          </div>
        </Card>

        <Card title="Grounding & qualidade" subtitle="claim-level analysis">
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <ClaimRow ok text="Janela de 7 dias para reembolsos." cite="refund-policy-2024.md#7-day-window" />
            <ClaimRow ok text="Abrir ticket tipo refund_request." cite="support-faq.md#partial-refunds" />
            <ClaimRow ok text="Categoria deve ser plano + motivo." cite="billing-rules.yaml#plan-changes" />
            <ClaimRow ok text="Escalar reembolsos parciais." cite="internal-runbook.md#escalation" />
            <ClaimRow ng text="Reembolsos parciais 'exigem 3 níveis de aprovação'." />
            <ClaimRow ng text="Limite de R$ 500 sem aprovação." />
          </div>
        </Card>
      </div>

      <div className="grid-2-eq">
        <Card title="Retrieval" subtitle={`${r.retrievedDocs} chunks · ordenados por score`} flush>
          <div className="citation-list" style={{ padding: 12 }}>
            {r.citations.map(c => (
              <div key={c.rank} className="citation">
                <div className="citation__rank">{c.rank}</div>
                <div className="citation__body">
                  <div className="citation__title">{c.title}</div>
                  <div className="citation__meta">{c.source} · {c.chunk}</div>
                </div>
                <div className="citation__score" style={{ color: c.score >= 0.8 ? "var(--ok)" : c.score >= 0.6 ? "var(--warn)" : "var(--err)" }}>
                  {c.score.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Citação por claim" subtitle="qual claim usou qual chunk" flush>
          <table className="t">
            <thead>
              <tr><th>Claim</th><th>Chunk</th><th>Score</th></tr>
            </thead>
            <tbody>
              {[
                { c: "Janela de 7 dias", k: "chunk_18", s: 0.91 },
                { c: "Ticket refund_request", k: "chunk_03", s: 0.84 },
                { c: "Categoria plano+motivo", k: "chunk_21", s: 0.76 },
                { c: "Escalação manual", k: "chunk_07", s: 0.68 },
                { c: "3 níveis de aprovação", k: "—", s: null },
                { c: "Limite R$ 500", k: "—", s: null },
              ].map((row, i) => (
                <tr key={i}>
                  <td className="t__name">{row.c}</td>
                  <td className="t__mono">{row.k}</td>
                  <td>{row.s != null ? <ScoreCell value={row.s} /> : <span className="faint mono">ungrounded</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </>
  );
}

function ClaimRow({ ok, ng, text, cite }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <div style={{
        width: 18, height: 18, borderRadius: 4, flexShrink: 0, marginTop: 1,
        background: ok ? "var(--ok-soft)" : "var(--err-soft)",
        border: `1px solid ${ok ? "oklch(0.78 0.15 158 / 0.4)" : "oklch(0.72 0.18 22 / 0.4)"}`,
        display: "grid", placeItems: "center",
        color: ok ? "var(--ok)" : "var(--err)",
      }}>
        <Icon name={ok ? "check" : "x"} size={10} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, color: ok ? "var(--text-dim)" : "var(--text)", lineHeight: 1.45 }}>{text}</div>
        {cite && <div className="mono faint" style={{ fontSize: 10.5, marginTop: 3 }}>↳ {cite}</div>}
        {ng && <div className="mono" style={{ fontSize: 10.5, marginTop: 3, color: "var(--err)" }}>↳ sem fonte recuperada</div>}
      </div>
    </div>
  );
}

Object.assign(window, { TracesScreen, TraceDetailScreen });
