import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18007/v1";
for (const width of [1280, 375]) {
  test(`curation and resumable investigation at ${width}px`, async ({ page, context, request, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    const stamp = `${Date.now()}-${width}`;
    const registered = await request.post(`${API}/auth/register`, { data: {
      email: `investigation-${stamp}@example.test`, name: "Curator", password: "Offline-test-123!",
      org_name: `Investigation ${stamp}`, project_name: "Curation",
    } });
    expect(registered.ok()).toBeTruthy();
    const session = await registered.json();
    const headers = { Authorization: `Bearer ${session.token}` };
    const workspace = session.workspace;
    const resolved = await request.get(`${API}/resolve?org_slug=${workspace.org_slug}&project_slug=${workspace.project_slug}`, { headers });
    const project = (await resolved.json()).project_id;
    const base = `/o/${workspace.org_slug}/p/${workspace.project_slug}`;
    const created = await request.post(`${API}/projects/${project}/datasets`, { headers: { ...headers, "Idempotency-Key": stamp }, data: { slug: `cases-${stamp}` } });
    expect(created.ok()).toBeTruthy();
    const dataset = await created.json();
    const keyResponse = await request.post(`${API}/projects/${project}/api-keys`, { headers, data: { name: "fixture", environment: "dev", scopes: ["ingest", "read"] } });
    const key = (await keyResponse.json()).key;
    const now = new Date().toISOString();
    const ingested = await request.post(`${API}/traces`, { headers: { "X-EvalOps-Key": key }, data: { traces: [{
      client_trace_id: stamp, name: "Fixture failure", environment: "dev", started_at: now, ended_at: now, status: "error",
      spans: [{ client_span_id: "root", type: "llm_call", name: "fixture", started_at: now, ended_at: now, status: "error",
        messages_in: [{ role: "user", content: "Question" }], messages_out: [{ role: "assistant", content: "Observed answer" }] }],
    }] } });
    expect(ingested.status()).toBe(202);
    const trace = (await ingested.json()).results[0].trace_id;
    await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    await page.goto(`${base}/evaluations/failures?env=dev`);
    await page.locator("summary").filter({ hasText: "Fixture failure" }).click();
    await page.getByLabel("Dataset para curadoria").selectOption(dataset.id);
    await page.getByRole("link", { name: "Criar caso a partir da evidência" }).click();
    await page.getByRole("button", { name: "Classificar origem do dataset" }).click();
    await expect(page.getByRole("heading", { name: "Saída observada" })).toBeVisible();
    await expect(page.getByLabel("Referência esperada JSON")).toHaveValue("null");
    await expect(page.getByLabel("Metadados JSON")).toHaveValue(/Observed answer/);
    await page.getByRole("button", { name: "Salvar caso em rascunho" }).click();
    await page.getByRole("link", { name: trace, exact: true }).click();
    await page.getByLabel("Referência esperada JSON").fill('{"assistant_message":"Reviewed answer"}');
    await page.getByLabel("Estado da referência").selectOption("reviewed");
    await page.getByLabel("Motivo da revisão humana").fill("Checked fixture manually");
    await page.getByRole("button", { name: "Salvar revisão do caso" }).click();
    await expect(page.getByRole("cell", { name: "Revisada por humano", exact: true })).toBeVisible();
    await page.goto(`${base}/evaluations/investigations`);
    await page.getByLabel("Título", { exact: true }).fill("Offline investigation");
    await page.getByLabel("Evidências (tipo:ID, uma por linha)").fill(`trace:${trace}`);
    await page.getByLabel("Próximos passos (um por linha)").fill("Review curated case");
    await page.getByRole("button", { name: "Salvar investigação" }).click();
    await expect(page).toHaveURL(/\/investigations\/investigation_/);
    const url = page.url();
    const id = url.split("/").pop()!;
    await page.getByLabel("Resumo técnico").fill("Case reviewed");
    await page.getByRole("button", { name: "Salvar investigação" }).click();
    await expect(page.getByText("Ambiente dev · revisão 2", { exact: true })).toBeVisible();
    expect(page.url()).toBe(url);
    const stale = await request.patch(`${API}/investigations/${id}`, { headers: { ...headers, "If-Match": "1", "Idempotency-Key": `stale-${stamp}` }, data: { state: { title: "Stale" } } });
    expect(stale.status()).toBe(409);
    await page.reload();
    await expect(page.getByLabel("Resumo técnico")).toHaveValue("Case reviewed");
    await expect(page.getByText("Revisão 1: Offline investigation", { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `/tmp/evalops-f2-${width}.png`, fullPage: true });
  });
}
