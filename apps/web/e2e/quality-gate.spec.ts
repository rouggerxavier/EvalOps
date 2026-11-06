import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";

const API = process.env.E2E_API_BASE_URL ?? "http://localhost:8000/v1";

test("Quality Gate: configurar, persistir e demonstrar review/pass/fail com tracing e rubrica reais", async ({ page, context, request, baseURL }) => {
  test.setTimeout(90_000);
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const registration = await request.post(`${API}/auth/register`, { data: {
    email: `gate-${stamp}@evalops.test`, name: "Quality Gate Demo", password: "demo-quality-gate-123!",
    org_name: `Demo Quality ${stamp}`, project_name: "Agente de atendimento",
  } });
  expect(registration.ok()).toBeTruthy();
  const session = await registration.json();
  const workspace = session.workspace;
  const headers = { Authorization: `Bearer ${session.token}` };
  const projectId = workspace.project_id;
  const path = `/o/${workspace.org_slug}/p/${workspace.project_slug}`;
  const gateUrl = `${API}/projects/${projectId}/quality-gate`;
  await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);

  await page.goto(path);
  const card = page.locator(".card").filter({ hasText: "Controle de qualidade · Quality Gate" });
  await expect(card).toContainText("Revisão necessária");
  await expect(card).toContainText("Salve os limites");
  await card.getByRole("link", { name: "Configurar limites" }).click();
  await expect(page.getByRole("heading", { name: "Quality Gate · limites de qualidade" })).toBeVisible();
  await page.getByLabel("Score mínimo de qualidade (%)").fill("80");
  await page.getByLabel("Taxa máxima de alucinação / sem suporte (%)").fill("5");
  await page.getByLabel("Custo médio máximo por trace (USD)").fill("0.05");
  await page.getByLabel("Latência p95 máxima (ms)").fill("2000");
  await page.getByLabel("Exigir zero violações críticas").check();
  await page.getByRole("button", { name: "Salvar Quality Gate" }).click();
  await expect(page).toHaveURL(/gate_saved=1/);
  await page.reload();
  await expect(page.getByLabel("Score mínimo de qualidade (%)")).toHaveValue("80");
  const stored = await (await request.get(gateUrl, { headers })).json();
  expect(stored.configured).toBe(true);
  expect(stored.min_score).toBe(0.8);
  expect(stored.max_ungrounded_rate).toBe(0.05);

  const key = await request.post(`${API}/projects/${projectId}/api-keys`, { headers, data: { name: "quality demo", environment: "prod", scopes: ["ingest", "read"] } });
  expect(key.ok()).toBeTruthy();
  const apiKey = (await key.json()).key;
  const now = new Date();
  const ended = new Date(now.getTime() + 1000);
  const ingest = await request.post(`${API}/traces`, { headers: { "X-EvalOps-Key": apiKey }, data: { traces: [{
    name: "rag.atendimento", environment: "prod", status: "ok", started_at: now.toISOString(), ended_at: ended.toISOString(),
    metadata: { support_rate: 1, output: "Resposta segura" },
    spans: [{ client_span_id: "generate", name: "llm.generate", type: "llm_call", status: "ok", started_at: now.toISOString(), ended_at: ended.toISOString(), cost_usd: 0.01, provider: "openai", model: "gpt-4o-mini", tokens_in: 100, tokens_out: 20 }],
  }] } });
  expect(ingest.status()).toBe(202);
  const traceId = (await ingest.json()).results[0].trace_id;
  const rubric = await request.post(`${API}/projects/${projectId}/rubrics`, { headers, data: { yaml_source: `
slug: atendimento-seguro
name: Atendimento seguro
description: Regra crítica de demonstração com avaliador determinístico.
threshold: 0.8
evaluators:
  - id: resposta-segura
    type: regex_match
    config:
      target: trace.output.assistant_message
      pattern: '^Resposta segura$'
automatic_fail_conditions:
  - slug: resposta-insegura
    description: Resposta fora do conteúdo permitido reprova automaticamente.
    evaluator_id: resposta-segura
` } });
  expect(rubric.ok()).toBeTruthy();
  const rubricId = (await rubric.json()).rubric.id;
  const evaluation = await request.post(`${API}/evaluations/run`, { headers, data: { trace_id: traceId, rubric_id: rubricId } });
  expect(evaluation.status()).toBe(201);
  const passed = await (await request.get(`${gateUrl}/status?environment=prod&window=7d`, { headers })).json();
  expect(passed.status).toBe("pass");
  expect(passed.metrics.critical_violations).toBe(0);

  await page.goto(path);
  await expect(card).toContainText("Resultado do gate: Aprovado");
  await expect(card).toContainText("100%");
  await expect(card).toContainText("0 violações");
  const screenshotDir = process.env.E2E_SCREENSHOT_DIR;
  if (screenshotDir) {
    await mkdir(screenshotDir, { recursive: true });
    await card.screenshot({ path: join(screenshotDir, "quality-gate-aprovado.png") });
  }

  await page.goto(`${path}/settings#quality-gate`);
  await page.getByLabel("Custo médio máximo por trace (USD)").fill("0.005");
  await page.getByRole("button", { name: "Salvar Quality Gate" }).click();
  await expect(page).toHaveURL(/gate_saved=1/);
  if (screenshotDir) await page.locator("#quality-gate").screenshot({ path: join(screenshotDir, "quality-gate-settings.png") });
  await page.goto(path);
  await expect(card).toContainText("Resultado do gate: Reprovado");
  await expect(card).toContainText("O limite configurado foi violado.");
  if (screenshotDir) await card.screenshot({ path: join(screenshotDir, "quality-gate-reprovado.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card).toBeVisible();
  const bounds = await card.boundingBox();
  expect(bounds!.width).toBeLessThanOrEqual(390);
  const mobileMetrics = card.locator(".quality-gate__metric");
  await expect(mobileMetrics).toHaveCount(5);
  for (const metric of await mobileMetrics.all()) {
    await metric.scrollIntoViewIfNeeded();
    await expect(metric).toBeInViewport();
    const metricBounds = await metric.boundingBox();
    expect(metricBounds!.x + metricBounds!.width).toBeLessThanOrEqual(390);
  }
  await card.getByRole("heading", { name: "Controle de qualidade · Quality Gate" }).scrollIntoViewIfNeeded();
  if (screenshotDir) await page.screenshot({ path: join(screenshotDir, "quality-gate-mobile.png"), style: "nextjs-portal { visibility: hidden; }" });

  // Existing modules remain reachable in the same authenticated project.
  for (const route of ["traces", "evaluations", "experiments"]) {
    const response = await page.goto(`${path}/${route}`);
    expect(response?.ok()).toBeTruthy();
    await expect(page.locator(".page-header__title").first()).toBeVisible();
    await expect(page.getByText("Algo deu errado", { exact: true })).toHaveCount(0);
  }
});
