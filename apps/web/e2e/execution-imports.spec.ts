import { test, expect } from "@playwright/test";
const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18007/v1";
for (const width of [1280, 375]) {
  test(`external capture remains declared evidence at ${width}px`, async ({ page, context, request, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    const stamp = `${Date.now()}-${width}`;
    const registered = await request.post(`${API}/auth/register`, { data: { email: `execution-${stamp}@example.test`, name: "Harness", password: "Offline-test-123!", org_name: `Harness ${stamp}`, project_name: "External capture" } });
    expect(registered.ok()).toBeTruthy();
    const session = await registered.json();
    const headers = { Authorization: `Bearer ${session.token}` };
    const project = session.workspace.project_id;
    async function post(path: string, data: unknown) {
      const response = await request.post(`${API}${path}`, { headers: { ...headers, "Idempotency-Key": crypto.randomUUID() }, data });
      expect(response.ok(), await response.text()).toBeTruthy();
      return response.json();
    }
    const dataset = await post(`/projects/${project}/datasets`, { slug: `harness-${stamp}`, task_type: "regression", task_schema: { target: { name: "value", unit: "1" } }, access: { environment: "dev" }, items: [{ sample_id: "s1", input: {}, expected_output: { value: 1 } }] });
    const snapshot = await post(`/datasets/${dataset.id}/snapshots`, { environment: "dev" });
    const model = await post(`/projects/${project}/model-versions`, { model: { name: "fixture", version_ref: "v1" }, access: { environment: "dev" } });
    const predictions = await post(`/projects/${project}/prediction-sets`, { environment: "dev", snapshot_id: snapshot.id, model_version_id: model.id, rows: [{ sample_id: "s1", prediction: { value: 1 } }] });
    const hash = `sha256:${"0".repeat(64)}`;
    const payload = { manifest: { mode: "application_adapter", environment: "dev", snapshot_id: snapshot.id, snapshot_hash: snapshot.content_hash,
      candidate: { application_ref: "fixture@v1", code_commit: "fixture-v1", code_dirty: false, config_digest: hash, model_versions: [model.id] },
      adapter: { id: "fixture", version: "1", environment_digest: hash, runtime: "fixture" }, initial_state_digest: hash, fixture_digests: [hash],
      limits: { max_cost_usd: "1.00", wall_time_s: 60, max_tool_calls: 2, max_tokens: 100, max_parallel: 1 } },
      result: { status: "succeeded", exit_reason: "Fixture complete", started_at: "2026-11-10T12:00:00Z", ended_at: "2026-11-10T12:00:01Z", prediction_set_id: predictions.id, capture_status: "complete", cost: { state: "unknown" } } };
    await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    const base = `/o/${session.workspace.org_slug}/p/${session.workspace.project_slug}/evaluations/executions`;
    await page.goto(base);
    await page.getByLabel("Arquivo de captura JSON").setInputFiles({ name: "capture.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(payload)) });
    await page.getByRole("button", { name: "Importar evidência de harness" }).click();
    await expect(page.getByRole("heading", { name: "Captura externa de execução", exact: true })).toBeVisible();
    await expect(page.getByText("Custo desconhecido", { exact: true })).toBeVisible();
    await expect(page.getByText("Proveniência parcial.", { exact: false })).toBeVisible();
    const id = page.url().split("/").pop()!;
    const response = await request.get(`${API}/executions/${id}`, { headers });
    expect(response.ok()).toBeTruthy();
    const capture = await response.json();
    expect(capture.decision).toBeNull();
    expect(capture.attempts[0].result.budget_reserved).toBeNull();
    await expect(page.getByText(`Manifest: ${capture.manifest_hash}`, { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `/tmp/evalops-f4-import-${width}.png`, fullPage: true });
  });
}
