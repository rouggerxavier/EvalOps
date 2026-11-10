import { test, expect } from "@playwright/test";
const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18007/v1";
for (const width of [1280, 375]) {
  test(`sealed plan admission and cancellation at ${width}px`, async ({ page, context, request, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    const stamp = `${Date.now()}-${width}`;
    const registration = await request.post(`${API}/auth/register`, { data: { email: `budget-${stamp}@example.test`, name: "Budget owner", password: "Offline-test-123!", org_name: `Budget ${stamp}`, project_name: "Admission" } });
    expect(registration.ok()).toBeTruthy();
    const session = await registration.json();
    const project = session.workspace.project_id;
    const headers = { Authorization: `Bearer ${session.token}` };
    async function post(path: string, data: unknown) {
      const response = await request.post(`${API}${path}`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data });
      expect(response.ok(), await response.text()).toBeTruthy(); return response.json();
    }
    const dataset = await post(`/projects/${project}/datasets`, { slug: `budget-${stamp}`, task_type: "regression", task_schema: { target: { name: "value", unit: "1" } }, access: { environment: "dev" }, items: [{ sample_id: "s1", input: {}, expected_output: { value: 1 } }] });
    const snapshot = await post(`/datasets/${dataset.id}/snapshots`, { environment: "dev" });
    const model = await post(`/projects/${project}/model-versions`, { model: { name: "fixture", version_ref: "1" }, access: { environment: "dev" } });
    const runner = await post(`/projects/${project}/runners`, { name: "Fixture", environments: ["dev"], adapter_versions: [{ id: "fixture", version: "1" }] });
    await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    const base = `/o/${session.workspace.org_slug}/p/${session.workspace.project_slug}/evaluations`;
    await page.goto(`${base}/runners`);
    await page.getByLabel("Budget da organização JSON").fill(JSON.stringify({ enabled: true, monthly_budget_usd: "0.01", max_parallel: 1 }));
    await page.getByRole("button", { name: "Salvar budget da organização" }).click();
    await expect(page.getByRole("heading", { name: "Budget da organização", exact: true }).locator("..").getByText("Revisão 1.", { exact: false })).toBeVisible();
    await page.getByLabel("Política de execução JSON").fill(JSON.stringify({ enabled: true, allowed_adapters: [{ id: "fixture", version: "1" }], max_cost_per_run_usd: "0.01", monthly_budget_usd: "0.01", max_parallel: 1 }));
    await page.getByRole("button", { name: "Salvar versão da política" }).click();
    await expect(page.getByRole("heading", { name: "Política do projeto", exact: true }).locator("..").getByText("Revisão 1.", { exact: false })).toBeVisible();
    const hash = `sha256:${"0".repeat(64)}`;
    const manifest = { mode: "application_adapter", environment: "dev", snapshot_id: snapshot.id, snapshot_hash: snapshot.content_hash,
      candidate: { application_ref: "fixture@1", code_commit: "fixture-v1", code_dirty: false, config_digest: hash, model_versions: [model.id] },
      adapter: { id: "fixture", version: "1", environment_digest: hash, runtime: "fixture" }, initial_state_digest: hash, fixture_digests: [hash],
      limits: { max_cost_usd: "0.01", wall_time_s: 60, max_tool_calls: 2, max_tokens: 100, max_parallel: 1 } };
    await page.goto(`${base}/executions`);
    await expect(page.getByLabel("Arquivo de plano JSON")).toBeEnabled();
    await page.getByLabel("Arquivo de plano JSON").setInputFiles({ name: "plan.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify({ runner_id: runner.id, manifest })) });
    await page.getByRole("button", { name: "Selar plano", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Plano selado", exact: true })).toBeVisible();
    const planId = page.url().split("/").pop()!;
    await page.getByRole("button", { name: "Reservar e enfileirar" }).click();
    await expect(page.getByRole("heading", { name: "Na fila", exact: true })).toBeVisible();
    const id = page.url().split("/").pop()!;
    const balance = await request.get(`${API}/executions/${id}/budget`, { headers });
    expect((await balance.json()).held_usd).toBe("0.01000000");
    await expect(page.locator('data[value="0.01000000"]')).toHaveCount(2);
    const denied = await request.post(`${API}/projects/${project}/executions`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data: { plan_id: planId } });
    expect(denied.status()).toBe(402);
    await page.getByRole("button", { name: "Solicitar cancelamento" }).click();
    await expect(page.getByRole("heading", { name: "Cancelada", exact: true })).toBeVisible();
    const after = await request.get(`${API}/executions/${id}/budget`, { headers });
    const budget = await after.json();
    expect(budget.held_usd).toBe("0.00000000");
    expect(budget.entries.filter((entry: { kind: string }) => entry.kind === "release")).toHaveLength(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `/tmp/evalops-f4-ledger-${width}.png`, fullPage: true });
  });
}
