import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overviewPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/page.tsx", import.meta.url),
  "utf8",
);
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.8 overview: server contract preserved (overview + traces + evals + rubrics)", () => {
  assert.match(overviewPage, /getOverview\(projectId, environment\)/);
  assert.match(overviewPage, /getTraces\(\{\s*projectId,\s*limit:\s*8,\s*environment\s*\}\)/);
  assert.match(overviewPage, /getProjectEvaluations\(projectId,\s*25\)/);
  assert.match(overviewPage, /getRubrics\(projectId\)/);
  assert.match(overviewPage, /resolveProject\(org,\s*project\)/);
  assert.match(overviewPage, /hasAuthToken\(\)/);
  assert.match(overviewPage, /<AuthRequiredPanel/);
});

test("P7.8 overview: header re-tune (Workspace eyebrow + ZIP-voice subtitle)", () => {
  assert.match(overviewPage, /Workspace · \{orgName\}/);
  assert.match(overviewPage, /Resumo de operacao · ambiente \{environmentLabel\}/);
  assert.match(
    overviewPage,
    /\{fmtInteger\(loadedTraces\)\} traces \/ \{fmtInteger\(loadedRubrics\)\} rubricas \/ \{fmtInteger\(loadedRuns\)\} runs carregados/,
  );
  assert.doesNotMatch(overviewPage, /Operacao · Overview/);
  assert.doesNotMatch(overviewPage, /leitura operacional com dados carregados do projeto/);
});

test("P7.8 overview: PageHeader keeps planned filter + refresh + run evaluation actions", () => {
  assert.match(overviewPage, /data-status="planned"/);
  assert.match(overviewPage, /Ultimos 7 dias/);
  assert.match(overviewPage, /title="Atualizar overview"/);
  assert.match(overviewPage, /Rodar avaliacao/);
});

test("P7.8 overview: attention strip rendered only with real problem traces", () => {
  assert.match(overviewPage, /function OverviewAlertBanner\(/);
  assert.match(overviewPage, /data-testid="overview-alert-banner"/);
  assert.match(overviewPage, /evo-overview-alert--\$\{variant\}/);
  assert.match(overviewPage, /if \(problemTraces\.length === 0\) return null/);
  assert.match(overviewPage, /precisam de atencao na amostra carregada/);
  assert.match(overviewPage, /<OverviewAlertBanner/);
  assert.match(overviewPage, /tracesHref=\{tracesHrefFor\}/);
});

test("P7.8 overview: attention strip variant + href derived from real status counts", () => {
  assert.match(
    overviewPage,
    /const errorCount = recentTraces\.filter\(\(trace\) => trace\.status === "error"\)\.length;/,
  );
  assert.match(
    overviewPage,
    /const partialCount = recentTraces\.filter\(\(trace\) => trace\.status === "partial"\)\.length;/,
  );
  assert.match(overviewPage, /const tab = errorCount > 0 \? "errors" : "flagged";/);
});

test("P7.8 overview: hero h2 uses mono title class", () => {
  assert.match(
    overviewPage,
    /<h2 className="evo-overview-hero__title">Visao geral honesta do projeto<\/h2>/,
  );
});

test("P7.8 overview: real data only — no invented signals or Potemkin modal", () => {
  assert.doesNotMatch(overviewPage, /PreviewActionModal/);
  assert.doesNotMatch(overviewPage, /SuggestionRow/);
  assert.doesNotMatch(overviewPage, /spans\/min/);
  assert.doesNotMatch(overviewPage, /aurora-rag/);
  assert.doesNotMatch(overviewPage, /errors_7d/);
  assert.doesNotMatch(overviewPage, /refund-golden-set/);
  assert.match(overviewPage, /kpis\.avg_score/);
  assert.match(overviewPage, /kpis\.error_rate/);
});

test("P7.8 overview: preserved cards (status / KPIs / next actions / traces / evals / signals / context / shortcuts)", () => {
  for (const token of [
    "<ProjectStatusCard",
    "<OverviewMetricCard",
    "<NextActions",
    "<RecentTracesCard",
    "<EvaluationSnapshotCard",
    "<OperationalSignals",
    "<ProjectContext",
    "evo-overview-shortcuts",
    "evo-overview-metric-grid",
    "evo-overview-main-grid",
  ]) {
    assert.ok(
      overviewPage.includes(token),
      `expected overview page to keep ${token}`,
    );
  }
});

test("P7.8 overview: CSS primitives scoped in .evo-shell (no :root leakage)", () => {
  assert.match(css, /\.evo-shell \.evo-overview-hero__title \{/);
  assert.match(css, /\.evo-shell \.evo-overview-alert \{/);
  assert.match(css, /\.evo-shell \.evo-overview-alert--error \{/);
  assert.match(css, /\.evo-shell \.evo-overview-alert__icon \{/);
  assert.match(css, /\.evo-shell \.evo-overview-alert__body \{/);
  assert.match(css, /\.evo-shell \.evo-overview-alert__cta \{/);
  const overviewBlock = css.match(/P7\.8 — Overview re-tune[\s\S]*$/);
  assert.ok(overviewBlock, "P7.8 CSS block missing");
  assert.doesNotMatch(overviewBlock[0], /^\s*:root\s*\{/m);
});
