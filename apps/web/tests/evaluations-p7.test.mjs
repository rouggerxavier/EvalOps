import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const evaluationsPage = readFileSync(
  new URL("../app/o/[org]/p/[project]/evaluations/page.tsx", import.meta.url),
  "utf8",
);
const distBars = readFileSync(new URL("../components/DistBars.tsx", import.meta.url), "utf8");
const rubricDrawer = readFileSync(new URL("../components/RubricDrawer.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("P7.9 evaluations: server contract preserved", () => {
  for (const token of [
    "getProjectEvaluations(resolved.project_id, EVALUATION_RUNS_LIMIT)",
    "getRubrics(resolved.project_id)",
    "getTraces({ projectId: resolved.project_id, limit: 20 })",
    "getRubricVersions(selectedRubric.id)",
    "triggerEvaluationAction",
    "resolveProject(org, project)",
    "hasAuthToken()",
    "<AuthRequiredPanel",
  ]) {
    assert.ok(
      evaluationsPage.includes(token),
      `expected evaluations page to keep ${token}`,
    );
  }
});

test("P7.9 evaluations: header re-tune (Qualidade eyebrow + ZIP-voice subtitle)", () => {
  assert.match(evaluationsPage, /Qualidade · Avaliações/);
  assert.match(evaluationsPage, /<h1 className="evo-page-header__title">Avaliações<\/h1>/);
  assert.match(
    evaluationsPage,
    /LLM-as-judge e heurísticas executadas sobre traces de produção · \{rubrics\.length\.toLocaleString\("pt-BR"\)\} rubrica\(s\) \/ \{runs\.length\.toLocaleString\("pt-BR"\)\} run\(s\) carregadas/,
  );
  assert.doesNotMatch(evaluationsPage, /Operação · Avaliações/);
  assert.doesNotMatch(evaluationsPage, /<h1 className="evo-page-header__title">Evaluations<\/h1>/);
  assert.doesNotMatch(
    evaluationsPage,
    /Avaliações LLM-as-judge e heurísticas rodadas sobre traces de produção\./,
  );
});

test("P7.9 evaluations: new Ver rubricas action between Rodar agora and Nova rubrica", () => {
  assert.match(evaluationsPage, /data-testid="evaluations-rubrics-link"/);
  assert.match(evaluationsPage, /<List size=\{13\} \/> Ver rubricas/);
  assert.match(
    evaluationsPage,
    /import \{[^}]*\bList\b[^}]*\} from "lucide-react"/,
  );
  const playIdx = evaluationsPage.indexOf("Rodar agora");
  const verIdx = evaluationsPage.indexOf("Ver rubricas");
  const novaIdx = evaluationsPage.indexOf("Nova rubrica");
  assert.ok(playIdx > 0 && verIdx > playIdx, "Ver rubricas must come after Rodar agora");
  assert.ok(novaIdx > verIdx, "Nova rubrica must come after Ver rubricas");
});

test("P7.9 evaluations: KPI label renamed to Rubricas ativas with hint preserved", () => {
  assert.match(evaluationsPage, /label="Rubricas ativas"/);
  assert.match(evaluationsPage, /hint="Fonte: getRubrics"/);
});

test("P7.9 evaluations: DistBars + RubricDrawer + triggerEvaluationAction preserved", () => {
  assert.match(evaluationsPage, /import \{ DistBars \}/);
  assert.match(evaluationsPage, /import \{ RubricDrawer \}/);
  assert.match(evaluationsPage, /<DistBars dist=\{dist\}/);
  assert.match(evaluationsPage, /<RubricDrawer/);
  assert.match(evaluationsPage, /rubric=\{selectedRubric\}/);
  assert.match(evaluationsPage, /action=\{triggerEvaluationAction\}/);
  assert.match(distBars, /export function DistBars/);
  assert.match(rubricDrawer, /yaml_source/);
});

test("P7.9 evaluations: planned controls + empty states preserved", () => {
  for (const token of [
    "data-status=\"planned\"",
    "disabled",
    "href=\"#run-evaluation\"",
    "Nenhuma rubrica cadastrada",
    "Criar rubrica",
    "Nenhuma run ainda",
    "traces.length === 0",
    "Ver traces",
  ]) {
    assert.ok(
      evaluationsPage.includes(token),
      `expected evaluations page to keep ${token}`,
    );
  }
});

test("P7.9 evaluations: real data only — no ZIP mocks or Potemkin modal", () => {
  assert.doesNotMatch(evaluationsPage, /PreviewActionModal/);
  assert.doesNotMatch(evaluationsPage, /EvaluationDrawer/);
  assert.doesNotMatch(evaluationsPage, /EndpointSnippet/);
  assert.doesNotMatch(evaluationsPage, /Math\.random/);
  assert.doesNotMatch(evaluationsPage, /grounded_in_retrieval/);
  assert.match(evaluationsPage, /aggregate_score/);
  assert.match(evaluationsPage, /buildDistribution/);
});

test("P7.9 evaluations: tabs + counts + dist bars CSS preserved", () => {
  assert.match(evaluationsPage, /evo-tab__count/);
  assert.match(evaluationsPage, /tab === "active"/);
  assert.match(evaluationsPage, /tab === "runs"/);
  assert.match(evaluationsPage, /tab === "paused"/);
  assert.match(css, /\.dist-bars/);
  assert.match(css, /\.evo-evaluations-summary/);
  assert.match(css, /\.evo-evaluations-layout/);
});
