import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18006/v1";
for (const width of [1280, 375]) {
  test(`offline regression shares persisted facts at ${width}px`, async ({ page, context, request, baseURL }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    const stamp = `${Date.now()}-${width}`;
    const registration = await request.post(`${API}/auth/register`, { data: {
      email: `offline-${stamp}@example.test`, name: "Offline Test", password: "Offline-test-123!",
      org_name: `Offline ${stamp}`, project_name: "Regression",
    } });
    expect(registration.ok()).toBeTruthy();
    const session = await registration.json();
    const workspace = session.workspace;
    const path = `/o/${workspace.org_slug}/p/${workspace.project_slug}/evaluations/tasks`;
    const headers = { Authorization: `Bearer ${session.token}` };
    await context.addCookies([{ name: "evalops_session", value: session.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    await page.goto(path);
    await expect(page.getByRole("heading", { name: "Regressão offline", exact: true })).toBeVisible();
    await page.getByLabel("Dataset (slug)").fill(`prices-${stamp}`);
    await page.getByLabel("Alvo", { exact: true }).fill("price");
    await page.getByLabel("Unidade", { exact: true }).fill("BRL");
    await page.getByLabel("Modelo", { exact: true }).fill("linear");
    await page.getByLabel("Versão declarada").fill("v1");
    const data = [1,2,3].map((expected, index) => ({ sample_id: `s${index+1}`, expected, predicted: [1,2,5][index], input: { x: index } }));
    await page.getByLabel("Importar arquivo JSON").setInputFiles({ name: "predictions.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(data)) });
    const submit = page.getByRole("button", { name: "Importar e avaliar" });
    await expect(submit).toBeEnabled();
    await submit.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/evaluations\/tasks\/evaluation_/);
    await expect(page.getByRole("heading", { name: "Inconclusivo", exact: true })).toBeVisible();
    const id = page.url().split("/").pop()!;
    const response = await request.get(`${API}/task-evaluations/${id}/metrics`, { headers });
    expect(response.ok()).toBeTruthy();
    const facts = (await response.json()).data;
    for (const fact of facts.filter((value: { value_type: string; scope: string }) => value.value_type === "scalar" && value.scope === "dataset")) {
      const row = page.getByRole("row").filter({ has: page.getByRole("cell", { name: fact.definition_id, exact: true }) });
      await expect(row.locator("data")).toHaveAttribute("value", String(fact.value));
    }
    await expect(page.getByText("Sem política de qualidade.", { exact: false })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.goto(path);
    await expect(page.getByRole("link", { name: id, exact: true })).toBeVisible();
    await page.getByLabel("Snapshot existente").selectOption({ index: 1 });
    await page.getByLabel("Modelo", { exact: true }).fill("linear");
    await page.getByLabel("Versão declarada").fill("v2");
    const improved = data.map(row => ({ ...row, predicted: row.expected }));
    await page.getByLabel("Importar arquivo JSON").setInputFiles({ name: "candidate.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(improved)) });
    await page.getByRole("button", { name: "Importar e avaliar" }).click();
    await expect(page).toHaveURL(/\/evaluations\/tasks\/evaluation_/);
    const candidateId = page.url().split("/").pop()!;
    expect(candidateId).not.toBe(id);
    await page.goto(path);
    await page.getByRole("combobox", { name: "Baseline", exact: true }).selectOption(id);
    await page.getByRole("combobox", { name: "Candidato", exact: true }).selectOption(candidateId);
    await page.getByRole("button", { name: "Comparar avaliações" }).click();
    await expect(page).toHaveURL(/\/tasks\/comparison\?/);
    await expect(page.getByRole("heading", { name: "Inconclusivo", exact: true })).toBeVisible();
    const comparisonUrl = new URL(page.url());
    const compared = await request.get(`${API}/experiments/${comparisonUrl.searchParams.get("experiment")}/runs/${comparisonUrl.searchParams.get("comparison_run")}?view=task_v1`, { headers });
    expect(compared.ok()).toBeTruthy();
    const comparison = (await compared.json()).run;
    expect(comparison.decision).toBe("inconclusive");
    expect(comparison.decision_reasons).toContain("insufficient_pairs");
    expect(comparison).not.toHaveProperty("passed");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: `/tmp/evalops-f1-${width}.png`, fullPage: true });
  });
}
