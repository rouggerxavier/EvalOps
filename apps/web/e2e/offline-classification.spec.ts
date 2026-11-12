import { test, expect } from "@playwright/test";
const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18007/v1";
for (const width of [1280, 375]) {
  test(`classification shares server matrix and metrics at ${width}px`, async ({ page, context, request, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    const stamp = `${Date.now()}-${width}`;
    const registration = await request.post(`${API}/auth/register`, { data: { email: `class-${stamp}@example.test`, name: "Classifier", password: "Offline-test-123!", org_name: `Class ${stamp}`, project_name: "Classification" } });
    expect(registration.ok()).toBeTruthy();
    const session = await registration.json();
    await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    const base = `/o/${session.workspace.org_slug}/p/${session.workspace.project_slug}/evaluations/tasks`;
    await page.goto(`${base}/classification`);
    await expect(page.getByRole("heading", { name: "Classificação offline", exact: true })).toBeVisible();
    await page.getByLabel("Dataset (slug)").fill(`classes-${stamp}`);
    await page.getByLabel("Modelo", { exact: true }).fill("logistic");
    await page.getByLabel("Versão declarada").fill("v1");
    const actual = ["no", "no", "yes", "yes"];
    const predicted = ["no", "yes", "yes", "no"];
    const scores = [.1, .4, .35, .8];
    const fixture = { items: actual.map((label, i) => ({ sample_id: `s${i}`, input: { group: i % 2 }, expected_output: { label }, metadata: { region: i < 2 ? "north" : "south" } })), rows: predicted.map((label, i) => ({ sample_id: `s${i}`, prediction: { label, class_order: ["no", "yes"], probabilities: [1-scores[i], scores[i]] } })) };
    await page.getByLabel("Segmentos JSON").fill('["region"]');
    await page.getByLabel("Importar arquivo de classificação JSON").setInputFiles({ name: "classification.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(fixture)) });
    await page.getByRole("button", { name: "Importar classificação e avaliar" }).click();
    await expect(page.getByRole("heading", { name: "Resultado de classificação", exact: true })).toBeVisible();
    const id = page.url().split("/").pop()!;
    const metrics = await request.get(`${API}/task-evaluations/${id}/metrics`, { headers: { Authorization: `Bearer ${session.token}` } });
    expect(metrics.ok()).toBeTruthy();
    const facts = (await metrics.json()).data;
    for (const fact of facts.filter((row: { value_type: string; scope: string; scope_key: string }) => row.value_type === "scalar" && row.scope === "dataset" && row.scope_key === "all")) {
      const row = page.getByRole("row").filter({ has: page.getByRole("cell", { name: fact.definition_id, exact: true }) }).filter({ has: page.getByRole("cell", { name: "all", exact: true }) });
      if (fact.value !== null) await expect(row.locator("data")).toHaveAttribute("value", String(fact.value));
    }
    await expect(page.getByRole("heading", { name: "Matriz de confusão", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Calibração binária", exact: true })).toBeVisible();
    expect(facts.find((fact: { definition_id: string; scope_key: string }) => fact.definition_id === "classification.accuracy" && fact.scope_key === "all").value).toBe(.5);
    expect(facts.some((fact: { definition_id: string; state: string; scope: string }) => fact.definition_id === "classification.roc_auc" && fact.scope === "group" && fact.state === "not_applicable")).toBeTruthy();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `/tmp/evalops-f3-${width}.png`, fullPage: true });
  });
}
