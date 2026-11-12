import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

const API = process.env.E2E_API_BASE_URL ?? "http://127.0.0.1:18143/v1";
const ARTIFACTS = process.env.E2E_RECOVERY_ARTIFACTS;
const OLD = "recovery-e2e-old-password";
const NEW = "😀".repeat(8);

test.describe("password recovery with fake mailbox", () => {
  test.skip(process.env.E2E_RECOVERY !== "1", "requires guarded local fake-mailbox server");
  for (const width of [1280, 375]) {
    test(`fragment → reset → fresh login at ${width}px`, async ({ page, context, request, baseURL }) => {
      const email = `recovery-${Date.now()}-${width}@example.invalid`;
      const accountResponse = await request.post(`${API}/auth/register`, { data: { name: "Recuperação QA", email, password: OLD } });
      expect(accountResponse.status()).toBe(201);
      const account = await accountResponse.json();
      const requestMetadata: string[] = [];
      page.on("request", (req) => requestMetadata.push(req.url(), JSON.stringify(req.headers())));
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/login");
      await page.getByRole("link", { name: "Esqueci minha senha" }).click();
      await expect(page.getByRole("heading", { name: "Recuperar senha" })).toBeVisible();
      await page.getByLabel("Email", { exact: true }).fill(email);
      await page.getByRole("button", { name: "Enviar link de recuperação" }).click();
      await expect(page.getByRole("status")).toContainText("Se existir uma conta com senha");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      if (ARTIFACTS) await page.screenshot({ path: path.join(ARTIFACTS, `recovery-forgot-${width}.jpg`), type: "jpeg", quality: 85 });
      const inbox = await request.get(`${API.replace(/\/v1$/, "")}/_test/inbox`, { params: { email } });
      const { link } = await inbox.json();
      expect(link).toMatch(/\/reset-password#[A-Za-z0-9_-]{43}$/);
      const token = link.split("#")[1];
      const response = await page.goto(link);
      expect(response!.headers()["referrer-policy"]).toBe("no-referrer");
      expect(response!.headers()["x-robots-tag"]).toBe("noindex, nofollow");
      expect(await response!.text()).not.toContain(token);
      await expect(page).toHaveURL(`${baseURL}/reset-password`);
      await expect(page.getByLabel("Nova senha", { exact: true })).toBeEnabled();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      expect(await page.content()).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
      expect(await page.evaluate(() => [...Object.values(localStorage), ...Object.values(sessionStorage)])).not.toContain(token);
      expect((await context.cookies()).some((cookie) => cookie.value.includes(token))).toBe(false);
      await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
      await page.getByLabel("Confirmar nova senha", { exact: true }).fill("mismatch-password");
      const submitted = page.waitForRequest((req) => req.method() === "POST" && new URL(req.url()).pathname === "/reset-password");
      await page.getByRole("button", { name: "Redefinir senha e entrar" }).click();
      const action = await submitted;
      await expect(page.getByRole("main").getByRole("alert")).toContainText("confirmação deve ser igual");
      expect(page.url()).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
      const foreign = await context.request.post(`${baseURL}/reset-password`, {
        headers: { "Next-Action": action.headers()["next-action"], "Content-Type": action.headers()["content-type"], Origin: "https://foreign.example.invalid" },
        data: action.postData()!,
      });
      expect([403, 500]).toContain(foreign.status());
      expect((await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${account.token}` } })).status()).toBe(200);
      if (ARTIFACTS) await page.screenshot({ path: path.join(ARTIFACTS, `recovery-reset-${width}.jpg`), type: "jpeg", quality: 85 });
      await page.getByLabel("Confirmar nova senha", { exact: true }).fill(NEW);
      await page.getByRole("button", { name: "Redefinir senha e entrar" }).click();
      await expect(page).toHaveURL(/\/login\?password_changed=1$/);
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
      expect((await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${account.token}` } })).status()).toBe(401);
      expect((await request.post(`${API}/auth/reset-password`, { data: { token, new_password: OLD } })).status()).toBe(400);
      await page.getByLabel("Email", { exact: true }).fill(email);
      await page.getByLabel("Senha", { exact: true }).fill(NEW);
      await page.getByRole("button", { name: "Entrar", exact: true }).click();
      await expect(page).toHaveURL(/\/(?:app|o\/.*)$/);
      const session = (await context.cookies()).find((cookie) => cookie.name === "evalops_session");
      expect(session).toBeDefined();
      expect((await request.get(`${API}/auth/session`, { headers: { Authorization: `Bearer ${session!.value}` } })).status()).toBe(200);
      expect(requestMetadata.some((value) => value.includes(token) || value.includes(OLD) || value.includes(encodeURIComponent(NEW)))).toBe(false);
      for (const logfile of [process.env.E2E_RECOVERY_API_LOG, process.env.E2E_RECOVERY_WEB_LOG].filter(Boolean)) {
        const logs = readFileSync(logfile!, "utf8");
        expect(logs.includes(token) || logs.includes(OLD) || logs.includes(NEW)).toBe(false);
      }
      await page.goBack();
      expect(page.url()).not.toContain(token);
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(token);
    });
  }
  test("invalid or missing fragment stays safe and offers a fresh link", async ({ page }) => {
    for (const fragment of ["", "#bad", "#reset-password", "#children", "#" + "x".repeat(43)]) {
      await page.goto(`/reset-password?error=__proto__${fragment}`);
      await expect(page).toHaveURL(/\/reset-password$/);
      if (fragment.length === 44) {
        await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
        await page.getByLabel("Confirmar nova senha", { exact: true }).fill(NEW);
        await page.getByRole("button", { name: "Redefinir senha e entrar" }).click();
      }
      await expect(page.getByRole("main").getByRole("alert")).toContainText("link é inválido");
      await expect(page.getByRole("link", { name: "Pedir novo link" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Redefinir senha" })).toBeVisible();
      expect(await page.getByRole("main").innerText()).not.toContain("__proto__");
    }
  });
  test("reopened link replaces the token in the same document", async ({ page, request, baseURL }) => {
    const email = `recovery-reopen-${Date.now()}@example.invalid`;
    expect((await request.post(`${API}/auth/register`, { data: { name: "Reabrir QA", email, password: OLD } })).status()).toBe(201);
    expect((await request.post(`${API}/auth/forgot-password`, { data: { email } })).status()).toBe(202);
    const { link } = await (await request.get(`${API.replace(/\/v1$/, "")}/_test/inbox`, { params: { email } })).json();
    const token = link.split("#")[1];
    await page.goto("/reset-password");
    await expect(page.getByLabel("Nova senha", { exact: true })).toBeDisabled();
    await page.evaluate(() => { (window as any).__recoveryDocument = document; });
    for (const fragment of ["x".repeat(43), "bad", token]) {
      await page.evaluate((hash) => { location.hash = hash; }, fragment);
      await expect(page).toHaveURL(`${baseURL}/reset-password`);
      expect(await page.evaluate(() => (window as any).__recoveryDocument === document)).toBe(true);
      if (fragment === "bad") {
        await expect(page.getByLabel("Nova senha", { exact: true })).toBeDisabled();
        await expect(page.getByRole("main").getByRole("alert")).toContainText("link é inválido");
      } else {
        await expect(page.getByLabel("Nova senha", { exact: true })).toBeEnabled();
        await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
      }
      expect(await page.evaluate(() => JSON.stringify(history.state))).not.toContain(fragment);
    }
    await page.getByLabel("Nova senha", { exact: true }).fill(NEW);
    await page.getByLabel("Confirmar nova senha", { exact: true }).fill(NEW);
    await page.getByRole("button", { name: "Redefinir senha e entrar" }).click();
    await expect(page).toHaveURL(/\/login\?password_changed=1$/);
    expect((await request.post(`${API}/auth/login`, { data: { email, password: NEW } })).status()).toBe(200);
  });
});
