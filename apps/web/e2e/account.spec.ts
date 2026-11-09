import { test, expect, type APIRequestContext } from "@playwright/test";
import path from "node:path";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18133/v1";
const ARTIFACTS = process.env.E2E_ACCOUNT_ARTIFACTS;
const OLD = "account-e2e-old-password";
const NEW = "account-e2e-new-password";

test.describe("authenticated account", () => {
  test.skip(process.env.E2E_ACCOUNT !== "1", "opt in against an isolated account API/database");

  async function register(request: APIRequestContext, password = OLD) {
    const email = `account-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
    const registered = await request.post(`${API}/auth/register`, { data: { name: "Conta QA", email, password } });
    expect(registered.status()).toBe(201);
    return { ...(await registered.json()), email };
  }

  test("no cookie redirects even when the web dev fallback exists", async ({ page }) => {
    await page.goto("/account");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Boas-vindas de volta" })).toBeVisible();
  });

  test("non-BMP current passwords are never truncated by HTML fields", async ({ page, context, request, baseURL }) => {
    const current = "😀".repeat(200);
    const next = "😀".repeat(8);
    const account = await register(request, current);
    await context.addCookies([{ name: "evalops_session", value: account.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
    await page.goto("/account");
    await page.getByLabel("Senha atual", { exact: true }).fill(current);
    await expect(page.getByLabel("Senha atual", { exact: true })).toHaveValue(current);
    await page.getByLabel("Nova senha", { exact: true }).fill(next);
    await page.getByLabel("Confirmar nova senha", { exact: true }).fill(next);
    await page.getByRole("button", { name: "Trocar senha e sair" }).click();
    await expect(page).toHaveURL(/\/login\?password_changed=1$/);
    expect((await request.post(`${API}/auth/login`, { data: { email: account.email, password: next } })).status()).toBe(200);
  });

  for (const width of [1280, 375]) {
    test(`Conta, topbar and keyboard at ${width}px`, async ({ page, context, request, baseURL }) => {
      const account = await register(request);
      await context.addCookies([{ name: "evalops_session", value: account.token, url: baseURL!, httpOnly: true, sameSite: "Lax" }]);
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`/o/${account.workspace.org_slug}/p/${account.workspace.project_slug}/traces`);
      const accountLink = page.getByRole("link", { name: "Conta", exact: true });
      await expect(accountLink).toBeVisible();
      await expect(page.getByRole("button", { name: "Sair", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      if (ARTIFACTS) await page.screenshot({ path: path.join(ARTIFACTS, `conta-topbar-${width}.jpg`), type: "jpeg", quality: 82 });
      await page.getByRole("button", { name: "Notificacoes", exact: true }).click();
      const panel = page.locator(".notifications-popover");
      await expect(panel).toBeVisible();
      const box = await panel.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      if (width === 375 && ARTIFACTS) await page.screenshot({ path: path.join(ARTIFACTS, "conta-sino-375.jpg"), type: "jpeg", quality: 82 });
      await page.getByRole("button", { name: "Notificacoes", exact: true }).click();
      await accountLink.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { name: "Conta", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.getByRole("link", { name: "Voltar ao workspace" }).focus();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "Sair", exact: true })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByLabel("Senha atual", { exact: true })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByLabel("Nova senha", { exact: true })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByLabel("Confirmar nova senha", { exact: true })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "Trocar senha e sair" })).toBeFocused();
      if (ARTIFACTS) await page.screenshot({ path: path.join(ARTIFACTS, `conta-${width}.jpg`), type: "jpeg", quality: 82 });
      await page.getByLabel("Senha atual", { exact: true }).fill(OLD);
      await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
      await page.getByLabel("Confirmar nova senha", { exact: true }).fill("mismatch-password");
      const submitted = page.waitForRequest((req) => req.method() === "POST" && new URL(req.url()).pathname === "/account");
      await page.getByRole("button", { name: "Trocar senha e sair" }).click();
      const actionRequest = await submitted;
      await expect(page.getByRole("region", { name: "Trocar senha" }).getByRole("alert")).toContainText("confirmação não corresponde");
      // Replay the real action with valid fields from a foreign origin: Next's same-origin gate must reject it.
      const foreign = await context.request.post(`${baseURL}/account`, {
        headers: { "Next-Action": actionRequest.headers()["next-action"], "Content-Type": actionRequest.headers()["content-type"], Origin: "https://foreign.example" },
        data: actionRequest.postData()!.replace("mismatch-password", NEW),
      });
      expect([403, 500]).toContain(foreign.status());
      expect((await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${account.token}` } })).status()).toBe(200);
      expect(page.url()).not.toContain(OLD);
      expect(page.url()).not.toContain(NEW);
      await page.getByLabel("Senha atual", { exact: true }).fill("incorrect-current");
      await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
      await page.getByLabel("Confirmar nova senha", { exact: true }).fill(NEW);
      await page.getByRole("button", { name: "Trocar senha e sair" }).click();
      await expect(page.getByRole("region", { name: "Trocar senha" }).getByRole("alert")).toContainText("Senha atual incorreta");
      await page.getByLabel("Senha atual", { exact: true }).fill(OLD);
      await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
      await page.getByLabel("Confirmar nova senha", { exact: true }).fill(NEW);
      await page.getByRole("button", { name: "Trocar senha e sair" }).click();
      await expect(page).toHaveURL(/\/login\?password_changed=1$/);
      await expect(page.getByRole("status")).toContainText("Todas as suas sessões foram encerradas");
      expect((await context.cookies()).some((cookie) => cookie.name === "evalops_session")).toBe(false);
      const stale = await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${account.token}` } });
      expect(stale.status()).toBe(401);
      await page.getByLabel("Email", { exact: true }).fill(account.email);
      await page.getByLabel("Senha", { exact: true }).fill(NEW);
      await page.getByRole("button", { name: "Entrar", exact: true }).click();
      await expect(page).toHaveURL(/\/(?:app|o\/.*)$/);
      const cookie = (await context.cookies()).find((item) => item.name === "evalops_session");
      expect(cookie).toBeDefined();
      expect((await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${cookie!.value}` } })).status()).toBe(200);
    });
  }
});
