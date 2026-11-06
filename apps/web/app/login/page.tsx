import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { AuthSidePanel } from "@/components/AuthSidePanel";
import { loginAction } from "@/lib/auth-actions";
import { getSession } from "@/lib/auth";

export const metadata = {
  title: "Entrar - EvalOps Studio",
};

type Search = Promise<{ error?: string; email?: string; redirected?: string }>;

export default async function LoginPage({ searchParams }: { searchParams: Search }) {
  const sp = await searchParams;
  const session = await getSession();
  if (session) {
    redirect("/app");
  }

  return (
    <div className="auth-shell">
      <div className="auth-grid">
        <section className="auth-pane">
          <Link className="auth-back" href="/">
            <ArrowLeft size={14} /> Voltar ao início
          </Link>
          <div className="auth-pane__form">
            <Link className="auth-brand" href="/">
              <img src="/brand/mark-evalops.svg" alt="" />
              <span>
                EvalOps<span className="sub">Studio</span>
              </span>
            </Link>
            <h1>Boas-vindas de volta</h1>
            <p className="auth-sub">
              Entre no seu workspace para continuar rastreando, avaliando e evoluindo seus agentes.
            </p>

            {sp?.error ? <p className="auth-error">{sp.error}</p> : null}

            <form action={loginAction}>
              <div className="auth-field">
                <label htmlFor="email">Email</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="voce@empresa.com"
                  autoComplete="email"
                  defaultValue={sp?.email ?? ""}
                  required
                />
              </div>
              <div className="auth-field">
                <div className="auth-field__row">
                  <label htmlFor="password">Senha</label>
                </div>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="********"
                  autoComplete="current-password"
                  required
                />
              </div>
              <button type="submit" className="mk-btn mk-btn--primary mk-btn--block mk-btn--lg">
                Entrar <ArrowRight />
              </button>
            </form>

            <p className="auth-foot">
              Ainda não tem workspace? <Link href="/register">Crie um</Link>
            </p>
          </div>
        </section>

        <AuthSidePanel variant="login" />
      </div>
    </div>
  );
}


