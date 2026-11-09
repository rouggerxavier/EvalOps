import { test, expect } from "@playwright/test";
import { createServer, type Server } from "node:http";

// Run only against a dedicated Next dev server pointing at this local fake API.
test.skip(process.env.E2E_HIDE_FAKE_API !== "1", "Requires isolated fake API; never runs against a shared backend.");
const base = "/o/org/p/project/traces";
const trace = { id: "trace-1", project_id: "owned-project", name: "Conversa de atendimento", environment: "prod", status: "ok",
  created_at: "2026-11-09T10:00:00Z", started_at: "2026-11-09T10:00:00Z", ended_at: "2026-11-09T10:00:01Z",
  duration_ms: 1000, total_cost_usd: 0, total_tokens_in: 0, total_tokens_out: 0, metadata: {}, tags: {} };
let server: Server;
let deleted = false;
let deleteStatus = 204;
let deletes: string[] = [];

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const url = new URL(req.url!, "http://fake.local");
    let status = 200;
    let body: unknown;
    if (url.pathname === "/v1/auth/session") {
      if (req.headers.authorization !== "Bearer personal-session") status = 401;
      body = { user: { id: "user", name: "Pessoa de teste", email: "test@example.test" }, workspace: null };
    } else if (url.pathname === "/v1/resolve") {
      body = { org_id: "org-id", project_id: "owned-project", org_name: "Organização", project_name: "Atendimento" };
    } else if (url.pathname === "/v1/traces/trace-1" && req.method === "DELETE") {
      deletes.push(req.headers.authorization ?? "");
      status = req.headers.authorization === "Bearer personal-session" ? deleteStatus : 401;
      if (status === 204) deleted = true;
      body = { detail: "SELECT secret FROM private_database" };
    } else if (url.pathname === "/v1/traces/trace-1") {
      status = deleted ? 404 : 200;
      body = { trace, spans: [], flags: [], feedback: [] };
    } else if (url.pathname === "/v1/traces") {
      body = { data: deleted ? [] : [trace], next_cursor: null };
    } else if (url.pathname === "/v1/projects") {
      body = { data: [{ id: "owned-project", slug: "project", name: "Atendimento" }] };
    } else if (/\/rubrics$|\/evaluations$|\/notifications$/.test(url.pathname)) {
      body = { data: [] };
    } else {
      status = 404;
      body = { detail: "not_found" };
    }
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(status === 204 ? undefined : JSON.stringify(body));
  });
  await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(18161, "127.0.0.1", resolve); });
});

test.afterAll(async () => { if (server) await new Promise<void>((resolve) => server.close(() => resolve())); });
test.beforeEach(async ({ context, baseURL }) => {
  deleted = false; deleteStatus = 204; deletes = [];
  await context.addCookies([{ name: "evalops_session", value: "personal-session", url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
});

for (const width of [1280, 375]) {
  test(`confirmation, keyboard, cancellation and successful hide at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${base}/trace-1?environment=`);
    const trigger = page.getByRole("button", { name: "Ocultar trace", exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Ocultar trace?", exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Avaliações históricas, cópias em datasets, exports, auditoria e backups");
    await expect(dialog.getByRole("button", { name: "Cancelar" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "Fechar" })).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(dialog.getByRole("button", { name: "Ocultar trace", exact: true })).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(dialog.getByRole("button", { name: "Fechar" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    expect(deletes).toEqual([]);
    await trigger.click();
    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(trigger).toBeFocused();
    expect(deletes).toEqual([]);
    await trigger.click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    const bounds = await dialog.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await page.screenshot({ path: test.info().outputPath(`hide-${width}.png`), animations: "disabled", style: "nextjs-portal { visibility: hidden; }" });
    await dialog.getByRole("button", { name: "Ocultar trace", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?environment=$`));
    await expect(page.getByRole("heading", { level: 1, name: "Traces" })).toBeVisible();
    expect(deletes).toEqual(["Bearer personal-session"]);
    await expect(page.getByText(trace.name, { exact: true })).toHaveCount(0);
  });
}

for (const [status, message] of [[401, "Sua sessão expirou"], [403, "não tem permissão"], [404, "pode já estar oculto"], [500, "Tente novamente"]] as const) {
  test(`failed DELETE ${status} remains safe and allows retry`, async ({ page }) => {
    deleteStatus = status;
    await page.goto(`${base}/trace-1?environment=prod`);
    await page.getByRole("button", { name: "Ocultar trace", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Ocultar trace?", exact: true });
    await dialog.getByRole("button", { name: "Ocultar trace", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText(message);
    await expect(dialog).not.toContainText("SELECT");
    await expect(page).toHaveURL(new RegExp(`${base}/trace-1\\?environment=prod$`));
    expect(deleted).toBe(false);
    deleteStatus = 204;
    await dialog.getByRole("button", { name: "Ocultar trace", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${base}\\?environment=prod$`));
  });
}

test("dashboard fallback cannot hide a trace", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto(`${base}/trace-1`);
  await page.getByRole("button", { name: "Ocultar trace", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Ocultar trace?", exact: true });
  await dialog.getByRole("button", { name: "Ocultar trace", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("conta pessoal");
  expect(deletes).toEqual([]);
});
