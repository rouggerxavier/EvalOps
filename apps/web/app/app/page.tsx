import { redirect } from "next/navigation";

import { getSession } from "@/lib/auth";

export const metadata = {
  title: "Abrindo seu workspace ? EvalOps Studio",
};

export const dynamic = "force-dynamic";

export default async function AppEntrypoint() {
  const session = await getSession();
  if (!session) {
    redirect("/login");
  }
  if (session.workspace) {
    const { org_slug, project_slug } = session.workspace;
    redirect(`/o/${org_slug}/p/${project_slug}`);
  }

  // Authenticated but no workspace yet - show a minimal entry card.
  return (
    <>
      <div className="bg-stage">
        <div className="bg-grid" />
      </div>
      <main className="entrypoint mk-wrap">
        <div className="entrypoint__card">
          <div className="spinner" aria-hidden="true" />
          <h1
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "var(--fg-1)",
              margin: "0 0 8px",
              letterSpacing: "-0.02em",
            }}
          >
            Nenhum workspace ainda
          </h1>
          <p style={{ color: "var(--fg-3)", fontSize: 14, margin: "0 0 20px" }}>
            Sua conta está autenticada, mas nenhum workspace foi encontrado. Crie um para continuar.
          </p>
          <p style={{ color: "var(--fg-4)", fontSize: 12, margin: 0 }}>
            <a href="/register" style={{ color: "var(--primary-300)", fontWeight: 600 }}>
              Criar workspace
            </a>
            &nbsp;&middot;&nbsp;
            <a href="/login" style={{ color: "var(--primary-300)", fontWeight: 600 }}>
              Entrar com outro usuário
            </a>
          </p>
        </div>
      </main>
    </>
  );
}


