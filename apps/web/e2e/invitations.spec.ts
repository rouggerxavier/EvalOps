import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const artifacts = process.env.E2E_INVITATIONS_ARTIFACTS;
if (artifacts) mkdirSync(artifacts, { recursive: true });

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18145/v1";
const control = API.replace(/\/v1$/, "");
const settings = "/o/org/p/project/settings";

test.describe("invitation UI with local contract fixture", () => {
  test.skip(process.env.E2E_INVITATIONS !== "1", "requires invitations-fake-api.mjs and isolated web server");
  test.beforeEach(async ({ request }) => { expect((await request.post(`${control}/_test/reset`)).ok()).toBe(true); });
  for (const width of [1280, 375]) {
    test(`owner invitation, errors, keyboard confirmation and transfer at ${width}px`, async ({ page, context, baseURL, request }) => {
      await context.addCookies([{ name: "evalops_session", value: "fixture-owner", url: baseURL! }]);
      await page.setViewportSize({ width, height: 900 });
      await page.goto(settings);
      await page.getByLabel("Email do convite").fill("invite@example.invalid");
      await page.getByRole("button", { name: "Enviar convite", exact: true }).click();
      await expect(page.getByRole("cell", { name: "Enviado", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Revogar convite de invite@example.invalid" }).click();
      await expect(page.getByRole("cell", { name: "Revogado", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Emitir novamente para invite@example.invalid" }).click();
      await expect(page.getByRole("cell", { name: "Enviado", exact: true })).toBeVisible();
      await request.post(`${control}/_test/failure`, { data: { detail: "membership_conflict" } });
      await page.getByRole("button", { name: "Remover member@example.invalid", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Remover membro?" });
      await expect(dialog.getByRole("button", { name: "Cancelar" })).toBeFocused();
      await page.keyboard.press("Tab"); await page.keyboard.press("Enter");
      await expect(dialog.getByRole("alert")).toContainText("Atualize a lista");
      await page.keyboard.press("Escape"); await expect(dialog).not.toBeVisible();
      await page.getByRole("button", { name: "Remover member@example.invalid", exact: true }).click();
      await page.getByRole("button", { name: "Confirmar remoção" }).click();
      await expect(page.getByRole("row", { name: /Member QA/ })).toHaveCount(0);
      if (artifacts) await page.screenshot({ path: path.join(artifacts, `memberships-owner-${width}.png`), fullPage: true });
      await page.getByRole("button", { name: "Transferir para viewer@example.invalid", exact: true }).click();
      await page.getByRole("button", { name: "Confirmar transferência" }).click();
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "Membros", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    });

    test(`fragment stays private and acceptance is explicit at ${width}px`, async ({ page, context, baseURL, request }) => {
      const token = "a".repeat(43);
      await context.addCookies([{ name: "evalops_session", value: "fixture-viewer", url: baseURL! }]);
      await page.setViewportSize({ width, height: 900 });
      const metadata: string[] = [];
      page.on("request", (req) => { metadata.push(req.url(), JSON.stringify(req.headers())); if (req.method() === "GET") metadata.push(req.postData() ?? ""); });
      const response = await page.goto(`/accept-invitation#${token}`);
      expect(response!.headers()["referrer-policy"]).toBe("no-referrer");
      await expect(page).toHaveURL(`${baseURL}/accept-invitation`);
      await expect(page.getByRole("button", { name: "Aceitar convite", exact: true })).toBeEnabled();
      expect(await response!.text()).not.toContain(token);
      expect(await page.content()).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain(token);
      expect((await (await request.get(`${control}/_test/state`)).json()).calls.some((call: { path: string }) => call.path === "/invitations/accept")).toBe(false);
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).focus(); await page.keyboard.press("Enter");
      await expect(page).toHaveURL(`${baseURL}/o/org/p/project`);
      expect(metadata.some((value) => value.includes(token))).toBe(false);
      await page.goto(`/accept-invitation#${"u".repeat(43)}`);
      await expect(page.getByRole("button", { name: "Aceitar convite", exact: true })).toBeEnabled();
      const before = (await (await request.get(`${control}/_test/state`)).json()).calls.filter((call: { path: string }) => call.path === "/projects").length;
      await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
      await expect(page.getByRole("status")).toContainText("acesso permanece restrito");
      if (artifacts) await page.screenshot({ path: path.join(artifacts, `invitation-restricted-${width}.png`), fullPage: true });
      await expect(page.getByRole("link", { name: "Abrir organização" })).toHaveCount(0);
      expect((await (await request.get(`${control}/_test/state`)).json()).calls.filter((call: { path: string }) => call.path === "/projects").length).toBe(before);
    });
  }
  test("viewer/member settings and direct keys expose no admin fetch or action", async ({ page, context, baseURL, request }) => {
    for (const role of ["viewer", "member"]) {
      await context.addCookies([{ name: "evalops_session", value: `fixture-${role}`, url: baseURL! }]);
      await page.goto(settings);
      await expect(page.getByRole("button", { name: "Enviar convite", exact: true })).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "Membros", exact: true })).toBeVisible();
      await page.goto("/o/org/p/project/keys");
      await expect(page.getByRole("status")).toContainText("Acesso restrito");
      const calls = (await (await request.get(`${control}/_test/state`)).json()).calls.filter((call: { userId: string }) => call.userId === role);
      expect(calls.some((call: { path: string }) => /invitations|api-keys|subscription|usage|quality-gate|evaluation-sampling/.test(call.path))).toBe(false);
    }
  });
  test("missing, expired, no-session and empty-organization accept states", async ({ page, context, baseURL }) => {
    await page.goto("/accept-invitation#bad");
    await expect(page.getByRole("main").getByRole("alert")).toContainText("link completo");
    await page.evaluate(() => { location.hash = "a".repeat(43); });
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("conta pessoal");
    await context.addCookies([{ name: "evalops_session", value: "fixture-viewer", url: baseURL! }]);
    await page.evaluate(() => { location.hash = "x".repeat(43); });
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page.getByRole("main").getByRole("alert")).toContainText("expirou ou já foi usado");
    await page.evaluate(() => { location.hash = "n".repeat(43); });
    await page.getByRole("button", { name: "Aceitar convite", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("ainda não tem projetos");
  });
});
