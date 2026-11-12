import { test, expect, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

const control = "http://127.0.0.1:18146";
const workspace = "/o/org/p/project";
const settings = `${workspace}/settings`;
const artifacts = process.env.E2E_INVITATIONS_ARTIFACTS;
if (artifacts) mkdirSync(artifacts, { recursive: true });
async function login(context: BrowserContext, request: APIRequestContext, user: string, baseURL: string) {
  const { token } = await (await request.get(`${control}/_test/session/${user}`)).json();
  await context.addCookies([{ name: "evalops_session", value: token, url: baseURL }]);
  return { Authorization: `Bearer ${token}` };
}
async function link(request: APIRequestContext, email: string) {
  const mail = await (await request.get(`${control}/_test/inbox?email=${encodeURIComponent(email)}`)).json();
  expect(mail.to).toBe(email);
  expect(mail.subject).toContain("Convite");
  const url = mail.body.match(/http:\/\/127\.0\.0\.1:3136\/accept-invitation#[A-Za-z0-9_-]{43}/)?.[0];
  expect(url).toBeTruthy();
  return url as string;
}
async function invite(page: Page, email: string, role = "viewer") {
  await page.getByLabel("Email do convite").fill(email);
  await page.getByLabel("Papel do convite").selectOption(role);
  await page.getByRole("button", { name: "Enviar convite", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: email }).getByRole("cell", { name: "Enviado", exact: true })).toBeVisible();
}
async function screenshot(page: Page, name: string) {
  if (artifacts) await page.screenshot({ path: `${artifacts}/${name}.png`, fullPage: true });
}

test.describe("R2 real API + PG16 + Redis + in-memory SMTP", () => {
  test.skip(process.env.E2E_INVITATIONS_REAL !== "1", "requires invitations_e2e_server.py and isolated Next dev 3136");
  test.setTimeout(120_000);
  test.beforeEach(async ({ request }) => { expect((await request.post(`${control}/_test/reset`)).ok()).toBe(true); });
  for (const width of [1280, 390]) {
    test(`new account registers in another tab, accepts once; replay and expired links fail ${width}px`, async ({ page, context, request, baseURL }) => {
      await page.setViewportSize({ width, height: 900 });
      await login(context, request, "owner", baseURL!);
      await page.goto(settings);
      const email = `newcomer-${width}-${Date.now()}@example.invalid`;
      await invite(page, email, "member");
      const url = await link(request, email);
      await invite(page, "recipient2@example.invalid");
      const expiredUrl = await link(request, "recipient2@example.invalid");
      expect((await (await request.post(`${control}/_test/expire?email=recipient2%40example.invalid`)).json()).expired).toBe(1);
      await page.reload();
      await expect(page.getByRole("row").filter({ hasText: "recipient2@example.invalid" }).getByRole("cell", { name: "Expirado", exact: true })).toBeVisible();
      await context.clearCookies();
      await page.goto(url);
      await expect(page.getByRole("button", { name: "Aceitar convite", exact: true })).toBeEnabled();
      const [tab] = await Promise.all([context.waitForEvent("page"), page.getByRole("link", { name: "criar conta em outra aba" }).click()]);
      await tab.getByLabel("Nome completo").fill("Newcomer QA");
      await tab.getByLabel("Email de trabalho").fill(email);
      await tab.getByLabel("Senha", { exact: true }).fill("QA-senha-forte-2026!");
      await tab.getByRole("button", { name: "Criar workspace" }).click();
      await tab.waitForURL(u => !u.pathname.startsWith("/register"));
      await tab.close();
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page).toHaveURL(`${baseURL}${workspace}`);
      const session = (await context.cookies()).find(c => c.name === "evalops_session")!.value;
      const resolved = await (await request.get(`${control}/v1/resolve?org_slug=org&project_slug=project`, { headers: { Authorization: `Bearer ${session}` } })).json();
      expect(resolved.membership).toEqual({ role: "member", permissions: ["read", "write"] });
      await page.goto(`${workspace}/prompts`);
      await expect(page.getByRole("button", { name: "Criar prompt", exact: true, includeHidden: true })).toBeAttached();
      await page.goto(settings);
      await expect(page.getByRole("heading", { name: "Membros", exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await screenshot(page, `real-newcomer-member-${width}`);
      // The consumed link must not grant anything a second time.
      await page.goto(url);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page.getByRole("main").getByRole("alert")).toContainText("expirou ou já foi usado");
      await login(context, request, "recipient2", baseURL!);
      await page.goto(expiredUrl);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page.getByRole("main").getByRole("alert")).toContainText("expirou ou já foi usado");
      await screenshot(page, `real-expired-${width}`);
      const state = await (await request.get(`${control}/_test/state`)).json();
      expect(state.memberships.recipient2).toBeUndefined();
      expect(Object.values(state.memberships).filter(role => role === "member")).toHaveLength(2);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
    test(`issue, correct-email accept, revoke, remove, last owner and transfer ${width}px`, async ({ page, context, request, baseURL }) => {
      await page.setViewportSize({ width, height: 900 });
      await login(context, request, "owner", baseURL!);
      await page.goto(settings);
      await invite(page, "recipient@example.invalid", "member");
      const url = await link(request, "recipient@example.invalid");
      const token = url.split("#")[1];
      await screenshot(page, `real-owner-${width}`);
      // The same real email token must fail for the owner, without consuming it.
      await page.goto(url);
      await expect(page).toHaveURL(`${baseURL}/accept-invitation`);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page.getByRole("main").getByRole("alert")).toContainText("expirou ou já foi usado");
      await login(context, request, "recipient", baseURL!);
      await page.evaluate((value) => { location.hash = value; }, token);
      await expect(page.getByRole("button", { name: "Aceitar convite", exact: true })).toBeEnabled();
      const metadata: string[] = [];
      page.on("request", req => { metadata.push(req.url(), JSON.stringify(req.headers())); });
      expect(await page.content()).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify([history.state, localStorage, sessionStorage]))).not.toContain(token);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page).toHaveURL(`${baseURL}${workspace}`);
      expect(metadata.some(value => value.includes(token))).toBe(false);
      const state = await (await request.get(`${control}/_test/state`)).json();
      expect(state.memberships.recipient).toBe("member");
      expect(JSON.stringify(state.jobs)).not.toContain(token);
      await page.goto(settings);
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await login(context, request, "owner", baseURL!);
      await page.goto(settings);
      await invite(page, "recipient2@example.invalid");
      const revoked = await link(request, "recipient2@example.invalid");
      await page.getByRole("button", { name: "Revogar convite de recipient2@example.invalid" }).click();
      await expect(page.getByRole("row").filter({ hasText: "recipient2@example.invalid" }).getByRole("cell", { name: "Revogado", exact: true })).toBeVisible();
      // Exercise last-owner rejection through the real UI.
      await page.getByRole("button", { name: "Remover owner@example.invalid", exact: true }).click();
      await expect(page.getByRole("dialog").getByRole("button", { name: "Cancelar" })).toBeFocused();
      await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
      await expect(page.getByRole("dialog").getByRole("alert")).toContainText("manter um owner");
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: "Remover recipient@example.invalid", exact: true }).click();
      await page.getByRole("button", { name: "Confirmar remoção" }).click();
      await expect(page.getByRole("row").filter({ hasText: "Recipient QA" })).toHaveCount(0);
      await page.getByRole("button", { name: "Transferir para viewer@example.invalid", exact: true }).click();
      await page.getByRole("button", { name: "Confirmar transferência" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Chaves de API", exact: true })).toHaveCount(0);
      const after = await (await request.get(`${control}/_test/state`)).json();
      expect(after.memberships.owner).toBe("member"); expect(after.memberships.viewer).toBe("owner");
      expect(after.memberships.recipient).toBeUndefined();
      await screenshot(page, `real-transfer-${width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await login(context, request, "recipient2", baseURL!);
      await page.goto(revoked);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page.getByRole("main").getByRole("alert")).toContainText("expirou ou já foi usado");
    });
  }
  test("no personal session, StrictMode fragment privacy, unknown role stays restricted", async ({ page, context, request, baseURL }) => {
    const reset = await (await request.post(`${control}/_test/reset`)).json();
    const headers = await login(context, request, "owner", baseURL!);
    const response = await request.post(`${control}/v1/organizations/${reset.organization_id}/invitations`, { headers, data: { email: "unknown@example.invalid", role: "member" } });
    // Existing members cannot be issued a new invitation: acceptance preservation is proved by API tests.
    expect(response.status()).toBe(409);
    const issued = await request.post(`${control}/v1/organizations/${reset.organization_id}/invitations`, { headers, data: { email: "recipient@example.invalid", role: "viewer" } });
    expect(issued.status()).toBe(202);
    const url = await link(request, "recipient@example.invalid");
    const token = url.split("#")[1];
    await context.clearCookies();
    const observed: string[] = [];
    page.on("request", req => { observed.push(req.url(), JSON.stringify(req.headers())); if (req.method() === "GET") observed.push(req.postData() ?? ""); });
    const get = await page.goto(url);
    expect(get!.headers()["referrer-policy"]).toBe("no-referrer");
    expect(await get!.text()).not.toContain(token);
    await expect(page).toHaveURL(`${baseURL}/accept-invitation`);
    await expect(page.getByRole("button", { name: "Aceitar convite", exact: true })).toBeEnabled();
    expect(await page.content()).not.toContain(token);
    expect(await page.evaluate(() => JSON.stringify([history.state, localStorage, sessionStorage]))).not.toContain(token);
    const before = await (await request.get(`${control}/_test/state`)).json();
    expect(before.calls.filter((c: any) => c.path === "/invitations/accept")).toHaveLength(0);
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("conta pessoal");
    await login(context, request, "recipient", baseURL!);
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page).toHaveURL(`${baseURL}${workspace}`);
    expect(observed.some(value => value.includes(token))).toBe(false);
    await page.goto(`${workspace}/prompts`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Criar prompt", exact: true })).toHaveCount(0);
    expect((await (await request.get(`${control}/_test/state`)).json()).memberships.recipient).toBe("viewer");
    // The invited account acquires a legacy membership before accepting: API must preserve it.
    await login(context, request, "owner", baseURL!);
    expect((await request.post(`${control}/v1/organizations/${reset.organization_id}/invitations`, { headers, data: { email: "recipient2@example.invalid", role: "member" } })).status()).toBe(202);
    const unknownLink = await link(request, "recipient2@example.invalid");
    expect((await request.post(`${control}/_test/membership/recipient2/legacy`)).ok()).toBe(true);
    await login(context, request, "recipient2", baseURL!);
    await page.goto(unknownLink);
    const preAccept = await (await request.get(`${control}/_test/state`)).json();
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("acesso permanece restrito");
    await expect(page.getByRole("status")).toContainText("legacy");
    expect(page.url()).toBe(`${baseURL}/accept-invitation`);
    const postAccept = await (await request.get(`${control}/_test/state`)).json();
    expect(postAccept.memberships.recipient2).toBe("legacy");
    expect(postAccept.calls.slice(preAccept.calls.length).filter((c: any) => c.path === "/projects")).toEqual([]);
    await screenshot(page, "real-unknown-acceptance");
    const denied = await request.get(`${control}/v1/resolve?org_slug=org&project_slug=project`, { headers: await login(context, request, "unknown", baseURL!) });
    expect(denied.status()).toBe(403);

  });
  for (const width of [1280, 390]) {
    test(`owner rows and unknown role never change implicitly; dialogs restore focus ${width}px`, async ({ page, context, request, baseURL }) => {
      await page.setViewportSize({ width, height: 900 });
      expect((await request.post(`${control}/_test/membership/recipient/owner`)).ok()).toBe(true);
      await login(context, request, "owner", baseURL!);
      await page.goto(settings);
      // Owner demotion exists only through transfer, including the current owner's own row.
      await expect(page.getByLabel("Novo papel de owner@example.invalid")).toHaveCount(0);
      await expect(page.getByLabel("Novo papel de recipient@example.invalid")).toHaveCount(0);
      const unknown = page.getByRole("row").filter({ hasText: "unknown@example.invalid" });
      await expect(unknown.getByLabel("Novo papel de unknown@example.invalid")).toHaveValue("");
      await expect(unknown.getByRole("option", { name: "Manter papel atual (legacy)" })).toBeDisabled();
      await unknown.getByRole("button", { name: "Salvar papel", exact: true }).click();
      const member = page.getByRole("row").filter({ hasText: "member@example.invalid" });
      await member.getByLabel("Novo papel de member@example.invalid").selectOption("viewer");
      await member.getByRole("button", { name: "Salvar papel", exact: true }).click();
      await expect(page.getByRole("status")).toContainText("Alteração concluída");
      const remove = page.getByRole("button", { name: "Remover viewer@example.invalid", exact: true });
      await remove.click();
      await expect(page.getByRole("dialog").getByRole("button", { name: "Cancelar" })).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(remove).toBeFocused();
      await remove.click();
      await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
      await expect(remove).toBeFocused();
      await remove.click();
      await page.getByRole("button", { name: "Confirmar remoção" }).click();
      await expect(page.getByRole("heading", { name: "Membros", exact: true })).toBeFocused();
      await expect(page.getByRole("row").filter({ hasText: "viewer@example.invalid" })).toHaveCount(0);
      const state = await (await request.get(`${control}/_test/state`)).json();
      expect(state.memberships).toMatchObject({ owner: "owner", recipient: "owner", unknown: "legacy", member: "viewer" });
      expect(state.memberships.viewer).toBeUndefined();
      expect(state.calls.filter((c: any) => c.method === "PATCH").map((c: any) => c.path)).toEqual([expect.stringMatching(/\/members\/member$/)]);
      await screenshot(page, `real-owner-unknown-rows-${width}`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });
  }
  test("self remove immediately refreshes personal permissions", async ({ page, context, request, baseURL }) => {
    expect((await request.post(`${control}/_test/membership/recipient/owner`)).ok()).toBe(true);
    await login(context, request, "owner", baseURL!);
    await page.goto(settings);
    await page.getByRole("button", { name: "Remover owner@example.invalid", exact: true }).click();
    await page.getByRole("button", { name: "Confirmar remoção" }).click();
    await expect(page).toHaveURL(`${baseURL}/app`);
    await expect(page.getByRole("heading", { name: "Nenhum workspace ainda" })).toBeVisible();
    const state = await (await request.get(`${control}/_test/state`)).json();
    expect(state.memberships.owner).toBeUndefined();
    expect(state.memberships.recipient).toBe("owner");
    await screenshot(page, "real-self-remove");
  });
  for (const role of ["viewer", "member"]) {
    test(`${role} has coherent menus and no admin fetch on real API`, async ({ page, context, request, baseURL }) => {
      await login(context, request, role, baseURL!);
      await page.goto(settings);
      await expect(page.getByRole("heading", { name: "Membros", exact: true })).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Chaves de API", exact: true })).toHaveCount(0);
      for (const [path, button] of [["prompts", "Criar prompt"], ["rubrics", "Criar rubrica"], ["datasets", "Criar dataset"], ["exports", "Criar export"]]) {
        await page.goto(`${workspace}/${path}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        if (role === "viewer") await expect(page.getByRole("button", { name: button, exact: true })).toHaveCount(0);
        else await expect(page.getByRole("button", { name: button, exact: true, includeHidden: true })).toBeAttached();
      }
      for (const path of ["experiments", "evaluations?modal=create", "evaluations?modal=run"]) {
        await page.goto(`${workspace}/${path}`);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        if (role === "viewer") await expect(page.getByRole("button", { name: /Criar experimento|Criar rubrica|Rodar avaliação/ })).toHaveCount(0);
      }
      await page.goto(`${workspace}/traces/trace`);
      await expect(page.getByRole("heading", { level: 1 })).toContainText("QA Trace");
      await expect(page.getByRole("button", { name: "Ocultar trace", exact: true })).toHaveCount(0);
      if (role === "viewer") {
        await expect(page.getByRole("button", { name: /Marcar para revisão|Repetir chamada LLM|Avaliar/ })).toHaveCount(0);
        await expect(page.getByRole("button", { name: /feedback/i })).toHaveCount(0);
      } else {
        await page.getByRole("button", { name: "Repetir chamada LLM", exact: true }).click();
        await expect(page.getByRole("dialog")).toBeVisible(); await page.keyboard.press("Escape");
      }
      await screenshot(page, `real-${role}-trace`);
      await page.goto(`${workspace}/keys`);
      await expect(page.getByRole("status")).toContainText("Acesso restrito");
      const state = await (await request.get(`${control}/_test/state`)).json();
      const calls = state.calls.filter((c: any) => c.user === role);
      expect(calls.filter((c: any) => /invitations|api-keys|subscription|usage|quality-gate|evaluation-sampling/.test(c.path))).toEqual([]);
    });
  }
});
