import Link from "next/link";

import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

type ProbeResult = {
  name: "liveness" | "readiness";
  status: "ok" | "fail";
  http_status: number | null;
  detail: string;
};

function apiRoot(): string {
  // getApiBaseUrl returns the /v1 prefixed URL; strip the suffix to reach the
  // unversioned /health/liveness and /health/readiness routes.
  const base = getApiBaseUrl();
  return base.replace(/\/v1\/?$/, "");
}

async function probe(name: "liveness" | "readiness"): Promise<ProbeResult> {
  const url = `${apiRoot()}/health/${name}`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    const body = (await res.json()) as { status?: string };
    if (!res.ok) {
      return { name, status: "fail", http_status: res.status, detail: body.status ?? "not_ready" };
    }
    return { name, status: "ok", http_status: res.status, detail: body.status ?? "ok" };
  } catch (error) {
    return {
      name,
      status: "fail",
      http_status: null,
      detail: error instanceof Error ? error.message : "unreachable",
    };
  }
}

export default async function HealthPage() {
  const [liveness, readiness] = await Promise.all([probe("liveness"), probe("readiness")]);
  const allOk = liveness.status === "ok" && readiness.status === "ok";

  return (
    <main style={{ padding: 32, maxWidth: 720, margin: "0 auto" }}>
      <h1 style={{ marginTop: 0, fontSize: 24 }}>Status do EvalOps</h1>
      <p style={{ color: "var(--fg-3, #888)", fontSize: 13 }}>
        Probes vivas do backend. Esta página não usa dados cacheados.
      </p>

      <section
        style={{
          marginTop: 16,
          padding: "12px 16px",
          borderRadius: 8,
          background: allOk ? "var(--ok-bg, #0f3a25)" : "var(--err-bg, #3a0f0f)",
          border: `1px solid ${allOk ? "var(--ok-border, #1a6b40)" : "var(--err-border, #6b1a1a)"}`,
          color: allOk ? "var(--ok, #6ae0a8)" : "var(--err, #ff6363)",
        }}
      >
        <strong>{allOk ? "Tudo operacional" : "Degradação detectada"}</strong>
      </section>

      <ul style={{ listStyle: "none", padding: 0, marginTop: 16, display: "grid", gap: 12 }}>
        {[liveness, readiness].map((row) => (
          <li
            key={row.name}
            style={{
              padding: "10px 14px",
              borderRadius: 8,
              border: "1px solid var(--border, #2a2a2a)",
              background: "var(--bg-2, #161616)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong style={{ textTransform: "capitalize" }}>{row.name}</strong>
              <code
                style={{
                  fontSize: 12,
                  color: row.status === "ok" ? "var(--ok, #6ae0a8)" : "var(--err, #ff6363)",
                }}
              >
                {row.http_status ?? "—"} · {row.detail}
              </code>
            </div>
          </li>
        ))}
      </ul>

      <p style={{ marginTop: 24, fontSize: 12, color: "var(--fg-3, #888)" }}>
        <Link href="/">Voltar ao dashboard</Link>
      </p>
    </main>
  );
}
