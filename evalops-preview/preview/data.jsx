/* =============================================================
   EvalOps Preview — Mock data + endpoint annotation registry.
   ALL ids/keys are masked; nothing here is real PII or secret.
   ============================================================= */

const WORKSPACE = {
  org: "acme",
  orgName: "ACME Industries",
  project: "aurora-support",
  projectName: "Aurora Support",
  environment: "prod",
  sdkVersion: "evalops-python 0.7.2",
};

// ------- KPIs -------
const KPIS = {
  traces: { value: 14287, delta: "+12.4%", dir: "up", spark: [82, 90, 86, 110, 124, 118, 138, 142, 156, 162, 172, 158, 174, 182] },
  latencyP95: { value: 1140, delta: "+38ms", dir: "down", spark: [980, 1020, 990, 1080, 1060, 1110, 1090, 1140, 1100, 1130, 1180, 1120, 1160, 1140] },
  cost: { value: 13.42, delta: "+8.1%", dir: "up", spark: [0.7, 0.8, 0.75, 0.9, 1.0, 1.1, 1.05, 1.2, 1.0, 1.15, 1.25, 1.18, 1.22, 1.34] },
  errorRate: { value: 0.018, delta: "-0.4pp", dir: "up", spark: [0.028, 0.026, 0.025, 0.022, 0.021, 0.019, 0.022, 0.02, 0.018, 0.017, 0.019, 0.018, 0.018, 0.018] },
  avgScore: { value: 0.84, delta: "+0.02", dir: "up", spark: [0.78, 0.79, 0.80, 0.79, 0.82, 0.81, 0.82, 0.83, 0.84, 0.83, 0.85, 0.84, 0.85, 0.84] },
};

// ------- Cost time series -------
const COST_BY_DAY = (() => {
  const today = new Date();
  const out = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    out.push({
      day: d.toISOString().slice(0, 10),
      label: `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`,
      cost: 0.4 + Math.random() * 1.2 + i * 0.04,
      traces: 600 + Math.floor(Math.random() * 700) + i * 40,
    });
  }
  return out;
})();

// ------- Model breakdown -------
const MODEL_BREAKDOWN = [
  { provider: "openai",    model: "gpt-4o-mini",      calls: 8420, cost: 4.238, latency: 612, share: 0.41 },
  { provider: "openai",    model: "gpt-4.1",          calls: 1206, cost: 6.810, latency: 1840, share: 0.32 },
  { provider: "anthropic", model: "claude-haiku-4.5", calls: 2310, cost: 1.472, latency: 480, share: 0.14 },
  { provider: "groq",      model: "llama-3.3-70b",    calls: 1840, cost: 0.521, latency: 220, share: 0.08 },
  { provider: "google",    model: "gemini-2.5-flash", calls:  920, cost: 0.408, latency: 510, share: 0.05 },
];

// ------- Trace fixtures -------
const TRACE_NAMES = {
  "trc_8f4a92d1": { name: "support.refund.flow",       service: "billing-agent",   isRag: true,  status: "partial", duration: 2840, tokensIn: 1240, tokensOut: 642, cost: 0.00821, model: "gpt-4.1", score: 0.42, env: "prod", ago: "3min", flagged: "schema_mismatch" },
  "trc_71bc40e2": { name: "billing.plan.change",       service: "billing-agent",   isRag: false, status: "error",   duration: 8120, tokensIn: 980,  tokensOut: 0,   cost: 0.00412, model: "gpt-4.1", score: null, env: "prod", ago: "8min", flagged: "timeout" },
  "trc_55ee2718": { name: "rag.answer.compose",        service: "aurora-rag",      isRag: true,  status: "partial", duration: 1980, tokensIn: 3420, tokensOut: 421, cost: 0.00612, model: "claude-haiku-4.5", score: 0.61, env: "prod", ago: "12min", flagged: "low_confidence" },
  "trc_2a91ffe7": { name: "chat.answer",               service: "aurora-rag",      isRag: true,  status: "ok",      duration: 920,  tokensIn: 2810, tokensOut: 382, cost: 0.00410, model: "claude-haiku-4.5", score: 0.91, env: "prod", ago: "14min", flagged: null },
  "trc_3df48a09": { name: "chat.answer",               service: "aurora-rag",      isRag: true,  status: "ok",      duration: 1080, tokensIn: 2640, tokensOut: 410, cost: 0.00390, model: "claude-haiku-4.5", score: 0.88, env: "prod", ago: "18min", flagged: null },
  "trc_91024c5b": { name: "tool.search.invoice",       service: "billing-agent",   isRag: false, status: "ok",      duration: 612,  tokensIn:  480, tokensOut: 128, cost: 0.00121, model: "gpt-4o-mini", score: null, env: "prod", ago: "22min", flagged: null },
  "trc_b48a0c11": { name: "rag.answer.compose",        service: "aurora-rag",      isRag: true,  status: "ok",      duration: 1240, tokensIn: 3120, tokensOut: 460, cost: 0.00510, model: "claude-haiku-4.5", score: 0.86, env: "prod", ago: "26min", flagged: null },
  "trc_7c12dd4e": { name: "support.refund.flow",       service: "billing-agent",   isRag: true,  status: "ok",      duration: 1810, tokensIn: 1810, tokensOut: 510, cost: 0.00714, model: "gpt-4.1", score: 0.82, env: "prod", ago: "31min", flagged: null },
  "trc_de9a2b18": { name: "chat.answer",               service: "aurora-rag",      isRag: true,  status: "ok",      duration: 1020, tokensIn: 2410, tokensOut: 390, cost: 0.00362, model: "claude-haiku-4.5", score: 0.84, env: "staging", ago: "38min", flagged: null },
  "trc_a01b7c63": { name: "summarize.ticket",          service: "tickets-agent",   isRag: false, status: "ok",      duration: 480,  tokensIn:  920, tokensOut: 220, cost: 0.00088, model: "gpt-4o-mini", score: null, env: "prod", ago: "42min", flagged: null },
  "trc_f5184e0d": { name: "agent.tool.route",          service: "tickets-agent",   isRag: false, status: "ok",      duration: 380,  tokensIn:  640, tokensOut: 140, cost: 0.00061, model: "llama-3.3-70b", score: null, env: "prod", ago: "47min", flagged: null },
  "trc_009c4ad8": { name: "rag.answer.compose",        service: "aurora-rag",      isRag: true,  status: "error",   duration: 5210, tokensIn: 2980, tokensOut: 0,   cost: 0.00128, model: "gpt-4.1", score: null, env: "prod", ago: "1h", flagged: "vector_db_timeout" },
  "trc_30dfa1e6": { name: "chat.answer",               service: "aurora-rag",      isRag: true,  status: "ok",      duration: 920,  tokensIn: 2510, tokensOut: 380, cost: 0.00378, model: "claude-haiku-4.5", score: 0.89, env: "prod", ago: "1h", flagged: null },
  "trc_8b78a4f0": { name: "billing.plan.change",       service: "billing-agent",   isRag: false, status: "ok",      duration: 1240, tokensIn: 1120, tokensOut: 380, cost: 0.00521, model: "gpt-4.1", score: null, env: "prod", ago: "1h", flagged: null },
  "trc_4c9032b1": { name: "support.refund.flow",       service: "billing-agent",   isRag: true,  status: "ok",      duration: 1640, tokensIn: 1810, tokensOut: 480, cost: 0.00682, model: "gpt-4.1", score: 0.78, env: "prod", ago: "2h", flagged: null },
};

const TRACES = Object.entries(TRACE_NAMES).map(([id, t]) => ({ id, ...t }));

// ------- Trace detail (extra context for one canonical RAG trace) -------
const TRACE_DETAIL = {
  "trc_8f4a92d1": {
    spans: [
      { id: "sp_01", name: "support.refund.flow",      kind: "root",      offset: 0,    duration: 2840 },
      { id: "sp_02", name: "policy.lookup",            kind: "tool",      offset: 40,   duration: 180 },
      { id: "sp_03", name: "retrieval.policies",       kind: "retrieval", offset: 240,  duration: 320 },
      { id: "sp_04", name: "embed.query",              kind: "embed",     offset: 280,  duration: 80 },
      { id: "sp_05", name: "llm.compose_answer",       kind: "llm",       offset: 620,  duration: 1640 },
      { id: "sp_06", name: "tool.create_refund_ticket",kind: "tool",      offset: 2280, duration: 410 },
      { id: "sp_07", name: "eval.refund.schema",       kind: "eval",      offset: 2700, duration: 130 },
    ],
    rag: {
      retrievedDocs: 6,
      avgScore: 0.71,
      groundedClaims: 4,
      ungroundedClaims: 2,
      hallucinationRisk: "medium",
      citations: [
        { rank: 1, title: "refund-policy-2024.md#7-day-window", score: 0.91, source: "policies/refund-policy-2024.md", chunk: "chunk_18" },
        { rank: 2, title: "support-faq.md#partial-refunds",    score: 0.84, source: "kb/support-faq.md",              chunk: "chunk_03" },
        { rank: 3, title: "billing-rules.yaml#plan-changes",   score: 0.76, source: "policies/billing-rules.yaml",    chunk: "chunk_21" },
        { rank: 4, title: "internal-runbook.md#escalation",    score: 0.68, source: "runbooks/internal-runbook.md",   chunk: "chunk_07" },
        { rank: 5, title: "refund-policy-2024.md#exceptions",  score: 0.62, source: "policies/refund-policy-2024.md", chunk: "chunk_19" },
        { rank: 6, title: "contract-template.md#sla",          score: 0.51, source: "legal/contract-template.md",     chunk: "chunk_44" },
      ],
      answerPreview:
        "Para reembolsos dentro da janela de 7 dias, o agente deve abrir um ticket de tipo `refund_request` " +
        "com a categoria do plano e o motivo informado pelo cliente. Reembolsos parciais não estão cobertos " +
        "pela política atual e exigem escalação manual ao time financeiro.",
    },
    metadata: {
      "trace.id": "trc_8f4a92d1",
      "service.name": "billing-agent",
      "environment": "prod",
      "user.ref": "u_*****c41",
      "session.id": "sess_2b80",
      "app.version": "1.4.2",
      "model.primary": "gpt-4.1",
      "rubric.attached": ["refund-schema-v3", "answer-grounding-v2"],
    },
    feedback: [
      { id: "fb_01", thumbs: "down", comment: "Resposta correta mas o ticket foi aberto com a categoria errada.", who: "ana@*****", at: "há 2min" },
    ],
    error: { type: "schema_mismatch", message: "refund.category não corresponde ao enum esperado: enterprise|consumer", at: "span sp_07" },
  },
};

// ------- Evaluations -------
const RUBRICS = [
  { id: "rb_01", slug: "answer-grounding-v2", version: 4, type: "llm-judge", desc: "Quão fundamentada está a resposta nos documentos recuperados.", model: "gpt-4o-mini", threshold: 0.8 },
  { id: "rb_02", slug: "refund-schema-v3",    version: 3, type: "heuristic", desc: "Valida shape do JSON do ticket de refund.", model: "—",          threshold: 1.0 },
  { id: "rb_03", slug: "tone-empathy-v1",     version: 1, type: "llm-judge", desc: "Tom empático e profissional no atendimento.", model: "gpt-4o-mini", threshold: 0.7 },
  { id: "rb_04", slug: "pii-leakage",         version: 2, type: "heuristic", desc: "Detecta vazamento de PII na resposta.",         model: "—",          threshold: 1.0 },
  { id: "rb_05", slug: "citation-precision",  version: 2, type: "llm-judge", desc: "Precisão das citações retornadas pelo RAG.",    model: "gpt-4o-mini", threshold: 0.75 },
];

const EVALUATIONS = [
  { id: "ev_01", rubricId: "rb_01", runs7d: 4218, avgScore: 0.84, pass: 0.81, lastRun: "2min", dist: [12, 28, 64, 320, 980, 1842] },
  { id: "ev_02", rubricId: "rb_02", runs7d: 1842, avgScore: 0.92, pass: 0.96, lastRun: "5min", dist: [4, 8, 22, 84, 240, 1484] },
  { id: "ev_03", rubricId: "rb_03", runs7d: 2104, avgScore: 0.78, pass: 0.74, lastRun: "11min", dist: [42, 86, 180, 480, 720, 596] },
  { id: "ev_04", rubricId: "rb_04", runs7d: 3892, avgScore: 0.99, pass: 0.998, lastRun: "1min", dist: [0, 0, 4, 12, 38, 3838] },
  { id: "ev_05", rubricId: "rb_05", runs7d: 1320, avgScore: 0.71, pass: 0.62, lastRun: "18min", dist: [60, 122, 240, 380, 320, 198] },
];

// ------- Endpoint registry: maps preview actions to real backend endpoints -------
// Inferred from apps/api routes and apps/web/lib/api.ts in the EvalOps codebase.
const ENDPOINTS = {
  // Overview
  overview:           { method: "GET",    path: "/v1/projects/{project_id}/overview",                                         desc: "Retorna KPIs, cost_by_day, model_breakdown e recent_flagged." },
  refreshOverview:    { method: "GET",    path: "/v1/projects/{project_id}/overview",                                         desc: "Recarregar overview com cursor de tempo." },

  // Traces
  listTraces:         { method: "GET",    path: "/v1/traces?project_id={project_id}&status=&environment=&name=&cursor=",     desc: "Lista paginada de traces." },
  getTrace:           { method: "GET",    path: "/v1/traces/{trace_id}",                                                       desc: "Retorna trace + spans + events + feedback." },
  flagTrace:          { method: "POST",   path: "/v1/traces/{trace_id}/flags",                                                 desc: "Marca trace como problemático para revisão." },
  rerunTrace:         { method: "POST",   path: "/v1/traces/{trace_id}/rerun",                                                 desc: "Reexecuta trace com mesmo prompt/inputs (planejado)." },
  compareTraces:      { method: "POST",   path: "/v1/traces/compare",                                                          desc: "Compara dois traces lado a lado (planejado)." },
  exportTraces:       { method: "POST",   path: "/v1/exports/jsonl",                                                           desc: "Cria job de exportação JSONL dos traces filtrados." },
  createFeedback:     { method: "POST",   path: "/v1/traces/{trace_id}/feedback",                                              desc: "Registra feedback humano (thumbs + comment)." },

  // Evaluations
  listEvaluations:    { method: "GET",    path: "/v1/projects/{project_id}/evaluations",                                       desc: "Lista runs de avaliação agrupadas por rubrica." },
  triggerEvaluation:  { method: "POST",   path: "/v1/evaluations",                                                              desc: "Dispara avaliação sync: { trace_id, rubric_id }." },
  listRubrics:        { method: "GET",    path: "/v1/projects/{project_id}/rubrics",                                            desc: "Lista rubricas YAML versionadas." },

  // Rubricas
  createRubric:       { method: "POST",   path: "/v1/rubrics",                                                                  desc: "Cria nova rubrica (YAML)." },
  publishRubric:      { method: "POST",   path: "/v1/rubrics/{rubric_id}/publish",                                              desc: "Publica nova versão da rubrica." },

  // Prompts
  listPrompts:        { method: "GET",    path: "/v1/projects/{project_id}/prompts",                                            desc: "Lista prompts versionados." },
  createPrompt:       { method: "POST",   path: "/v1/prompts",                                                                  desc: "Cria nova versão de prompt." },

  // Datasets
  listDatasets:       { method: "GET",    path: "/v1/projects/{project_id}/datasets",                                           desc: "Lista datasets para experimentos." },
  createDataset:      { method: "POST",   path: "/v1/datasets",                                                                 desc: "Cria dataset a partir de traces selecionados." },

  // Experimentos
  listExperiments:    { method: "GET",    path: "/v1/projects/{project_id}/experiments",                                        desc: "Lista experimentos A/B de prompt/modelo." },
  createExperiment:   { method: "POST",   path: "/v1/experiments",                                                              desc: "Cria experimento A/B (planejado)." },

  // Keys
  listKeys:           { method: "GET",    path: "/v1/projects/{project_id}/api-keys",                                           desc: "Lista API keys mascaradas." },
  createKey:          { method: "POST",   path: "/v1/api-keys",                                                                 desc: "Cria nova API key (retorna só uma vez)." },
  revokeKey:          { method: "DELETE", path: "/v1/api-keys/{key_id}",                                                        desc: "Revoga API key." },

  // Exports
  listExports:        { method: "GET",    path: "/v1/projects/{project_id}/exports",                                            desc: "Lista jobs de exportação." },
  createExport:       { method: "POST",   path: "/v1/exports",                                                                  desc: "Cria novo export JSONL." },
  downloadExport:     { method: "GET",    path: "/v1/exports/{export_id}/download",                                             desc: "Baixa arquivo do export pronto." },
};

// Module placeholder summaries (Prompts/Rubricas/Datasets/Experimentos/Chaves/Exports)
const MODULES = {
  prompts: {
    title: "Prompts",
    desc: "Versionamento de prompts com diff e rollback. Cada versão fica rastreada por hash e linkada aos traces que a usaram.",
    counts: [{ label: "Prompts", value: "12" }, { label: "Versões", value: "47" }, { label: "Em produção", value: "5" }],
    items: [
      { name: "support.refund.system", versions: 6, current: "v6", usedBy: "billing-agent", lastUpdate: "2d" },
      { name: "rag.compose.answer",    versions: 9, current: "v9", usedBy: "aurora-rag",    lastUpdate: "4h" },
      { name: "tickets.summarize",     versions: 3, current: "v3", usedBy: "tickets-agent", lastUpdate: "1w" },
      { name: "chat.system",           versions: 12, current: "v12", usedBy: "aurora-rag",  lastUpdate: "1d" },
    ],
    endpoints: ["listPrompts", "createPrompt"],
  },
  rubrics: {
    title: "Rubricas",
    desc: "Rubricas YAML versionadas, executadas como LLM-as-judge ou heurística sobre traces selecionados.",
    counts: [{ label: "Rubricas", value: "5" }, { label: "LLM-judge", value: "3" }, { label: "Heurísticas", value: "2" }],
    items: RUBRICS.map(r => ({ name: r.slug, versions: r.version, current: `v${r.version}`, usedBy: r.type, lastUpdate: "—" })),
    endpoints: ["listRubrics", "createRubric", "publishRubric"],
  },
  datasets: {
    title: "Datasets",
    desc: "Coletâneas de traces curados (input/output/expected). Servem como golden set para experimentos e regressão.",
    counts: [{ label: "Datasets", value: "8" }, { label: "Items", value: "2.4k" }, { label: "Em uso", value: "3" }],
    items: [
      { name: "refund-golden-set",      versions: 2, current: "rows: 420",  usedBy: "experimento-12", lastUpdate: "3d" },
      { name: "rag-grounding-eval",     versions: 4, current: "rows: 1.2k", usedBy: "experimento-09", lastUpdate: "1w" },
      { name: "tone-empathy-samples",   versions: 1, current: "rows: 180",  usedBy: "—",              lastUpdate: "2w" },
    ],
    endpoints: ["listDatasets", "createDataset"],
  },
  experiments: {
    title: "Experimentos",
    desc: "Compara prompts ou modelos em um dataset versionado. Reporta delta de score, custo e latência.",
    counts: [{ label: "Experimentos", value: "14" }, { label: "Rodando", value: "1" }, { label: "Comparações", value: "32" }],
    items: [
      { name: "rag-compose vs claude-haiku-4.5", versions: 1, current: "concluído", usedBy: "rag-grounding-eval", lastUpdate: "6h" },
      { name: "refund-system v5 vs v6",           versions: 1, current: "rodando",   usedBy: "refund-golden-set",  lastUpdate: "agora" },
      { name: "tickets-summarize gpt-4o vs llama", versions: 1, current: "concluído", usedBy: "—",                 lastUpdate: "2d" },
    ],
    endpoints: ["listExperiments", "createExperiment"],
  },
  keys: {
    title: "Chaves API",
    desc: "Chaves de ingestão usadas pelo SDK Python. Exibidas mascaradas após a criação; segredo cru só é mostrado uma vez.",
    counts: [{ label: "Chaves ativas", value: "4" }, { label: "Revogadas", value: "1" }, { label: "Em uso (24h)", value: "3" }],
    items: [
      { name: "prod-default",     versions: "evk_prod_••••a14f", current: "ativa",    usedBy: "aurora-rag",      lastUpdate: "8min" },
      { name: "ci-runner",        versions: "evk_ci_••••97ab",   current: "ativa",    usedBy: "github-actions",  lastUpdate: "1h" },
      { name: "staging-eng",      versions: "evk_stg_••••3c01",  current: "ativa",    usedBy: "billing-agent",   lastUpdate: "3d" },
      { name: "old-laptop-rouger",versions: "evk_dev_••••5d22",  current: "revogada", usedBy: "—",               lastUpdate: "12d" },
    ],
    endpoints: ["listKeys", "createKey", "revokeKey"],
  },
  exports: {
    title: "Exports",
    desc: "Jobs de exportação JSONL de traces filtrados. Útil para fine-tune offline ou compartilhar evidência com terceiros.",
    counts: [{ label: "Jobs (30d)", value: "21" }, { label: "Concluídos", value: "19" }, { label: "Em fila", value: "0" }],
    items: [
      { name: "traces-refund-2026-05-19",    versions: "1.2 MB",  current: "pronto",   usedBy: "Rouger X.",  lastUpdate: "12min" },
      { name: "rag-grounding-golden-set",    versions: "4.8 MB",  current: "pronto",   usedBy: "Rouger X.",  lastUpdate: "2h" },
      { name: "tickets-summaries-q2",        versions: "2.1 MB",  current: "pronto",   usedBy: "Ana M.",     lastUpdate: "1d" },
      { name: "all-errors-last-7d",          versions: "—",       current: "expirado", usedBy: "—",          lastUpdate: "31d" },
    ],
    endpoints: ["listExports", "createExport", "downloadExport"],
  },
};

// Notifications (top-right bell)
const NOTIFICATIONS = [
  { id: "n1", title: "Rubrica answer-grounding-v2 publicada",  meta: "Rouger X. · há 2min",  kind: "info" },
  { id: "n2", title: "1 trace com schema_mismatch em refund",  meta: "há 3min",              kind: "warn" },
  { id: "n3", title: "Vector DB timeout (3 traces)",           meta: "há 1h",                kind: "err" },
];

Object.assign(window, {
  WORKSPACE, KPIS, COST_BY_DAY, MODEL_BREAKDOWN, TRACES, TRACE_DETAIL,
  RUBRICS, EVALUATIONS, ENDPOINTS, MODULES, NOTIFICATIONS,
});
