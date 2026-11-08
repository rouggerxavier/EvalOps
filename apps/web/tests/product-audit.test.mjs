import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const PROJECT = "app/o/[org]/p/[project]";

function sources(dir) {
  return readdirSync(new URL(`../${dir}`, import.meta.url)).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(new URL(`../${path}`, import.meta.url)).isDirectory()) return sources(path);
    return /\.tsx?$/.test(name) ? [path] : [];
  });
}

test("no page tells people to install the third-party evalops package", () => {
  for (const path of [...sources("app"), ...sources("components")]) {
    // The docs may name it only to warn against it.
    const lines = read(path).split("\n").filter((line) => !line.includes("não instale"));
    assert.doesNotMatch(lines.join("\n"), /pip install evalops/, path);
    assert.doesNotMatch(read(path), /evk_live_/, path);
  }
});

test("docs quickstart records the model call", () => {
  assert.match(read("app/docs/page.tsx"), /span\.set_llm\(/);
  assert.match(read("app/docs/page.tsx"), /pip install -e packages\/sdk-python/);
});

test("trace page shows the conversation and evaluation results", () => {
  const page = read(`${PROJECT}/traces/[trace]/page.tsx`);
  assert.match(page, /<TraceConversation /);
  assert.match(page, /<TraceEvaluations /);
  assert.match(page, /getTraceEvaluations\(/);
  assert.match(page, /return hasRag \? "rag" : "conversation"/);
  assert.match(page, /detail\.flags\.map/);
  const evaluations = read(`${PROJECT}/traces/[trace]/trace-evaluations.tsx`);
  assert.match(evaluations, /score\.reasoning/);
  assert.match(evaluations, /raised_flags/);
  assert.match(read(`${PROJECT}/traces/[trace]/trace-conversation.tsx`), /messages_out/);
});

test("trace model comes from the API before metadata", () => {
  assert.match(read("lib/trace-display.ts"), /return trace\.model \?\? metadataString/);
});

test("empty environment filter beats the cookie, and the chip can clear it", () => {
  assert.match(read("lib/active-env.ts"), /if \(qpEnv === ""\) return undefined/);
  assert.match(read("components/EvoTopbar.tsx"), /\["all", "prod", "staging", "dev"\]/);
  assert.match(read("components/AppShell.tsx"), /: "all";/);
  assert.match(read("lib/actions.ts"), /environment === "all"[\s\S]{0,60}store\.delete\(ENV_COOKIE\)/);
  assert.match(read(`${PROJECT}/traces/page.tsx`), /baseParams\.set\("environment", ""\)/);
  assert.match(read(`${PROJECT}/evaluations/page.tsx`), /getProjectEvaluations\(resolved\.project_id, EVALUATION_RUNS_LIMIT, environment\)/);
});

test("evaluate scope can be created on screen and is not preselected", () => {
  assert.match(read(`${PROJECT}/keys/page.tsx`), /name="scopes" value="evaluate" style/);
});

test("settings shows plan and usage instead of linking to a missing page", () => {
  const settings = read(`${PROJECT}/settings/page.tsx`);
  assert.match(settings, /<PlanUsage/);
  assert.doesNotMatch(settings, /\/usage`/);
  assert.match(read(`${PROJECT}/exports/page.tsx`), /<PlanUsage/);
});

test("rubric form starts from YAML the parser accepts", () => {
  const modal = read(`${PROJECT}/evaluations/evaluations-modals.tsx`);
  assert.doesNotMatch(modal, /type: builtin/);
  assert.match(modal, /name: Nova rubrica/);
});

test("trace list filters by period, tag, user, model, score and failures, and the topbar searches everything", () => {
  const page = read(`${PROJECT}/traces/page.tsx`);
  for (const name of ["since", "until", "tag", "user_ref", "model", "score_lt", "failed"]) {
    assert.match(page, new RegExp(`name="${name}"`), name);
  }
  assert.match(page, /for \(const \[key, value\] of Object\.entries\(filters\)\) baseParams\.set\(key, value\)/);
  assert.match(page, /key === "tag" && !\/\^\[\^:\]\+:\.\+\$\/\.test\(value\)/);
  const api = read("lib/api.ts");
  assert.match(api, /\["conversation_id", "since", "until", "tag", "user_ref", "model", "q"\]/);
  assert.match(api, /params\.set\("score_lt"/);
  const topbar = read("components/EvoTopbar.tsx");
  assert.match(topbar, /name="q" placeholder="Buscar por nome, id, usuário ou conversa\.\.\."/);
  assert.doesNotMatch(topbar, /name="name"/);
});

test("conversation turns are listed on the trace and filterable in the list", () => {
  const detail = read(`${PROJECT}/traces/[trace]/page.tsx`);
  assert.match(detail, /getTraces\(\{ projectId: t\.project_id, conversation_id: conversationId, limit: 50 \}\)/);
  assert.match(detail, /title="Conversa"/);
  assert.match(detail, /\[\.\.\.conversation\.data\]\.reverse\(\)/);
  assert.match(detail, /este turno/);
  assert.match(detail, /turn\.redacted \? <span className="tag">redigido<\/span>/);
  const list = read(`${PROJECT}/traces/page.tsx`);
  assert.match(list, /conversation_id: filters\.conversation_id/);
  assert.match(list, /withoutFilterHref\("conversation_id"\)/);
});

test("etapa 4 screens survive narrow screens, impossible dates and hydration", () => {
  const css = read("app/globals.css");
  assert.match(css, /\.card__body--flush \{ padding: 0; overflow-x: auto; \}/);
  assert.match(css, /\.table-wrap \{\n  overflow-x: auto;/);
  assert.match(read(`${PROJECT}/traces/page.tsx`), /!isRealDate\(value\)/);
  assert.doesNotMatch(read("components/ui/AreaChart.tsx"), /Math\.random/);
  assert.match(read(`${PROJECT}/traces/[trace]/page.tsx`), /conversation_id=\$\{encodeURIComponent\(conversationId\)\}&environment=`/);
  assert.doesNotMatch(read(`${PROJECT}/rubrics/page.tsx`), /versão\{/);
});

test("auth pages promise nothing that does not exist", () => {
  const login = read("app/login/page.tsx");
  assert.doesNotMatch(login, /name="remember"|30 dias/);
  assert.doesNotMatch(login, /SSO|plano Team/);
  for (const path of ["app/login/page.tsx", "app/register/page.tsx"]) {
    assert.doesNotMatch(read(path), /href="#"|Termos|Política de Privacidade|dicas de setup/, path);
  }
  const panel = read("components/AuthSidePanel.tsx");
  assert.doesNotMatch(panel, /Maya Halil|drift|1M traces|retenção de 90 dias|Self-host/);
});

test("landing SDK card shows only the Python SDK and records the model call", () => {
  const showcase = read("components/SDKShowcase.tsx");
  assert.doesNotMatch(showcase, /TypeScript|OpenTelemetry/);
  assert.match(showcase, /evalops\.set_trace\(/);
  assert.match(showcase, /span\.set_llm\(/);
});

test("docs quickstart traces the conversation with a real key prefix", () => {
  const docs = read("app/docs/page.tsx");
  assert.match(docs, /evalops\.set_trace\(conversation_id=/);
  assert.match(docs, /messages_out=\[/);
  // Keys are minted as evk_{environment}_ (apps/api/app/security.py).
  assert.match(docs, /api_key="evk_(dev|staging|prod)_\.\.\.", project="[^"]+", environment="\1"/);
});

test("evaluations has no paused tab without a data source", () => {
  assert.doesNotMatch(read(`${PROJECT}/evaluations/page.tsx`), /paused|Pausadas|pausadas automaticamente/);
});

test("how it works describes only features that exist", () => {
  const pipeline = read("components/HowItWorksPipeline.tsx");
  assert.doesNotMatch(pipeline, /Promova|entre prompts, modelos|na ingestão|fine-tuning|Ready to deploy/);
});
