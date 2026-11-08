import { test, expect, type BrowserContext, type Page } from "@playwright/test";

const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8000/v1";
const ORG_SLUG = process.env.E2E_ORG_SLUG ?? "my-org";
const PROJECT_SLUG = process.env.E2E_PROJECT_SLUG ?? "my-project";
const TEST_EMAIL = process.env.E2E_EMAIL ?? "e2e+smoke@evalops.local";
const TEST_PASSWORD = process.env.E2E_PASSWORD ?? "evalops-e2e-pw-1!";
const TEST_NAME = process.env.E2E_NAME ?? "E2E Smoke";
const SEED_EMAIL = process.env.E2E_SEED_EMAIL ?? "dev@evalops.local";

const PROJECT_BASE = `/o/${ORG_SLUG}/p/${PROJECT_SLUG}`;

const ROUTES: { path: string; heading: RegExp; label: string }[] = [
  { path: PROJECT_BASE, heading: /^Visão geral$/, label: "overview" },
  { path: `${PROJECT_BASE}/traces`, heading: /^Traces$/, label: "traces list" },
  { path: `${PROJECT_BASE}/traces/compare`, heading: /Comparar traces/, label: "traces compare" },
  { path: `${PROJECT_BASE}/evaluations`, heading: /Avaliações/, label: "evaluations" },
  { path: `${PROJECT_BASE}/prompts`, heading: /^Prompts$/, label: "prompts" },
  { path: `${PROJECT_BASE}/rubrics`, heading: /^Rubricas$/, label: "rubrics" },
  { path: `${PROJECT_BASE}/datasets`, heading: /^Datasets$/, label: "datasets" },
  { path: `${PROJECT_BASE}/experiments`, heading: /Experimentos/, label: "experiments" },
  { path: `${PROJECT_BASE}/keys`, heading: /^Chaves de API$/, label: "keys" },
  { path: `${PROJECT_BASE}/exports`, heading: /^Exports$/, label: "exports" },
  { path: `${PROJECT_BASE}/settings`, heading: /^Ajustes$/, label: "settings" },
];

async function obtainToken(): Promise<string> {
  const tryEndpoints: Array<{ path: string; body: object }> = [
    {
      path: "/auth/login",
      body: { email: TEST_EMAIL, password: TEST_PASSWORD },
    },
    {
      path: "/auth/register",
      body: { name: TEST_NAME, email: TEST_EMAIL, password: TEST_PASSWORD },
    },
    {
      path: "/auth/login",
      body: { email: SEED_EMAIL, password: TEST_PASSWORD },
    },
  ];
  let lastError = "no attempts";
  for (const attempt of tryEndpoints) {
    const res = await fetch(`${API_BASE_URL}${attempt.path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(attempt.body),
    });
    if (res.ok) {
      const body = (await res.json()) as { token?: string };
      if (body.token) return body.token;
      lastError = "ok response without token field";
    } else {
      lastError = `${attempt.path} ${res.status}`;
    }
  }
  throw new Error(`failed to obtain auth token: ${lastError}`);
}

async function seedSession(context: BrowserContext, baseURL: string | undefined): Promise<void> {
  const token = await obtainToken();
  const url = new URL(baseURL ?? "http://localhost:3000");
  await context.addCookies([
    {
      name: "evalops_session",
      value: token,
      domain: url.hostname,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
      secure: false,
    },
  ]);
}

async function expectNoErrorBoundary(page: Page) {
  const errorBoundary = page.locator("text=/Algo deu errado|Something went wrong/i");
  await expect(errorBoundary).toHaveCount(0);
}

test.describe("Phase 8 cockpit smoke", () => {
  test.beforeEach(async ({ context, baseURL }) => {
    await seedSession(context, baseURL);
  });

  for (const route of ROUTES) {
    test(`renders ${route.label} at ${route.path}`, async ({ page }) => {
      for (const width of [1280, 375]) {
        await page.setViewportSize({ width, height: 900 });
        const response = await page.goto(route.path);
        expect(response?.ok(), `navigation to ${route.path} returned ${response?.status()}`).toBeTruthy();
        await expect(page.getByRole("heading", { level: 1 })).toHaveText(route.heading);
        await expectNoErrorBoundary(page);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      }
    });
  }

  test("global shortcut G T navigates to traces", async ({ page }) => {
    await page.goto(PROJECT_BASE);
    await page.keyboard.press("g");
    await page.keyboard.press("t");
    await page.waitForURL(new RegExp(`${PROJECT_BASE}/traces(\\?|$)`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Traces$/);
  });

  test("mobile menu keeps keyboard focus and closes on escape, navigation and resize", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto(PROJECT_BASE);
    const toggle = page.locator('button[aria-controls="ops-sidebar"]');
    const menu = page.getByRole("dialog", { name: "Navegação principal" });
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const first = menu.getByRole("link", { name: "EvalOps Studio" });
    const last = menu.getByRole("link", { name: "Documentação" });
    await expect(first).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(last).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(first).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toBeFocused();
    await page.keyboard.press("Enter");
    await menu.getByRole("link", { name: /^Traces/ }).click();
    await page.waitForURL(new RegExp(`${PROJECT_BASE}/traces$`));
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.press("Enter");
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(menu).toHaveCount(0);
    await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
  });
});
