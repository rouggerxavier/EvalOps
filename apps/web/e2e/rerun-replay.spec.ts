/**
 * Fase E — e2e do fluxo rerun + worker arq.
 *
 * Requer stack completa (api + worker + redis + web + postgres).
 * Skip automático se a API não estiver acessível.
 *
 * Setup mínimo:
 *   docker compose up postgres redis api worker web
 *   pnpm --filter @evalops/web exec playwright test e2e/rerun-replay.spec.ts
 */
import { test, expect } from "@playwright/test";

const API_BASE_URL = process.env.E2E_API_BASE_URL ?? "http://localhost:8000/v1";
const ORG_SLUG = process.env.E2E_ORG_SLUG ?? "my-org";
const PROJECT_SLUG = process.env.E2E_PROJECT_SLUG ?? "my-project";
const TEST_EMAIL = process.env.E2E_EMAIL ?? "e2e+smoke@evalops.local";
const TEST_PASSWORD = process.env.E2E_PASSWORD ?? "evalops-e2e-pw-1!";
const TEST_NAME = process.env.E2E_NAME ?? "E2E Smoke";
const REPLAY_TIMEOUT_MS = Number(process.env.E2E_REPLAY_TIMEOUT_MS ?? 30_000);
const POLL_INTERVAL_MS = 1_500;

async function obtainToken(): Promise<string> {
  for (const body of [
    { email: TEST_EMAIL, password: TEST_PASSWORD },
    { name: TEST_NAME, email: TEST_EMAIL, password: TEST_PASSWORD, _register: true },
  ]) {
    const path = "_register" in body ? "/auth/register" : "/auth/login";
    const { _register: _r, ...payload } = body as Record<string, unknown> & { _register?: boolean };
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const json = (await res.json()) as { token?: string };
      if (json.token) return json.token;
    }
  }
  throw new Error("could not obtain auth token");
}

async function apiUp(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL.replace(/\/v1\/?$/, "")}/health/liveness`, {
      signal: AbortSignal.timeout(2_000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

test.describe("rerun trace produces real completed trace", () => {
  test.beforeAll(async () => {
    test.skip(!(await apiUp()), "API offline — pular e2e de replay (precisa do stack docker compose)");
  });

  test("clicking Reexecutar produces a completed trace via arq worker", async ({ page, request }) => {
    const token = await obtainToken();

    const projectResolve = await request.get(
      `${API_BASE_URL}/resolve?org_slug=${ORG_SLUG}&project_slug=${PROJECT_SLUG}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(projectResolve.ok()).toBeTruthy();
    const project = (await projectResolve.json()) as { project_id: string };

    const apiKeyRes = await request.post(`${API_BASE_URL}/projects/${project.project_id}/api-keys`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { name: "e2e-rerun", environment: "prod", scopes: ["ingest", "read"] },
    });
    expect(apiKeyRes.ok()).toBeTruthy();
    const apiKey = (await apiKeyRes.json()).key as string;

    const now = new Date();
    const ingestRes = await request.post(`${API_BASE_URL}/traces`, {
      headers: { "X-EvalOps-Key": apiKey, "Content-Type": "application/json" },
      data: {
        traces: [
          {
            client_trace_id: `e2e_${now.getTime()}`,
            name: "rag.answer.compose",
            service: "e2e",
            environment: "prod",
            started_at: now.toISOString(),
            ended_at: new Date(now.getTime() + 500).toISOString(),
            status: "ok",
            tags: {},
            metadata: {},
            spans: [
              {
                client_span_id: "sp_llm",
                type: "llm_call",
                name: "llm.generate",
                started_at: now.toISOString(),
                ended_at: new Date(now.getTime() + 400).toISOString(),
                status: "ok",
                provider: "openai",
                model: "gpt-4o-mini",
                messages_in: [{ role: "user", content: "ping" }],
                messages_out: [{ role: "assistant", content: "pong" }],
                tokens_in: 1,
                tokens_out: 1,
                events: [],
              },
            ],
          },
        ],
      },
    });
    expect(ingestRes.status()).toBe(202);
    const original = (await ingestRes.json()).results[0].trace_id as string;

    const rerunRes = await request.post(`${API_BASE_URL}/traces/${original}/rerun`, {
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      data: { model: null, variables: {} },
    });
    expect(rerunRes.ok()).toBeTruthy();
    const newId = (await rerunRes.json()).new_trace_id as string;

    const deadline = Date.now() + REPLAY_TIMEOUT_MS;
    let finalStatus = "unknown";
    while (Date.now() < deadline) {
      const traceRes = await request.get(`${API_BASE_URL}/traces/${newId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (traceRes.ok()) {
        const body = (await traceRes.json()) as { trace?: { metadata?: { replay_status?: string }; status?: string } };
        finalStatus = body.trace?.metadata?.replay_status ?? "unknown";
        if (finalStatus === "completed" || finalStatus === "failed") break;
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }

    expect(finalStatus, `replay_status final after ${REPLAY_TIMEOUT_MS}ms`).toBe("completed");

    await page.context().addCookies([
      {
        name: "evalops_session",
        value: token,
        domain: new URL("http://localhost:3000").hostname,
        path: "/",
        httpOnly: true,
        sameSite: "Lax",
        secure: false,
      },
    ]);
    await page.goto(`/o/${ORG_SLUG}/p/${PROJECT_SLUG}/traces/${newId}`);
    await expect(page.locator(".badge", { hasText: "replay · completed" })).toBeVisible();
  });
});
