import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { AuthSidePanel } from "@/components/AuthSidePanel";
import { registerAction } from "@/lib/auth-actions";
import { getSession } from "@/lib/auth";

export const metadata = {
  title: "Crie seu workspace - EvalOps Studio",
};

type Search = Promise<{ error?: string; email?: string; name?: string }>;

export default async function RegisterPage({ searchParams }: { searchParams: Search }) {
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
            <h1>Crie seu workspace</h1>
            <p className="auth-sub">
              Rastreie seu primeiro agente em menos de cinco minutos. Gratuito durante o beta &mdash; sem cartão.
            </p>

            {sp?.error ? <p className="auth-error">{sp.error}</p> : null}

            <form action={registerAction}>
              <div className="auth-field">
                <label htmlFor="name">Nome completo</label>
                <input
                  id="name"
                  name="name"
                  type="text"
                  placeholder="Ada Lovelace"
                  autoComplete="name"
                  defaultValue={sp?.name ?? ""}
                  required
                />
              </div>
              <div className="auth-field">
                <label htmlFor="email">Email de trabalho</label>
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
                <label htmlFor="password">Senha</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder="Pelo menos 8 caracteres"
                  autoComplete="new-password"
                  required
                  minLength={8}
                />
              </div>
              <div className="auth-field">
                <label htmlFor="org_name">Nome do workspace (opcional)</label>
                <input
                  id="org_name"
                  name="org_name"
                  type="text"
                  placeholder="Rogue Labs"
                  autoComplete="organization"
                />
              </div>
              <label className="auth-checkbox">
                <input type="checkbox" name="terms" required defaultChecked /> Eu concordo com os{" "}
                <a href="#" style={{ color: "var(--primary-300)", marginLeft: 4 }}>Termos</a>
                &nbsp;e&nbsp;
                <a href="#" style={{ color: "var(--primary-300)" }}>Política de Privacidade</a>
              </label>
              <button type="submit" className="mk-btn mk-btn--primary mk-btn--block mk-btn--lg">
                Criar workspace <ArrowRight />
              </button>
            </form>

            <p className="auth-foot">
              Já tem workspace? <Link href="/login">Entrar</Link>
            </p>
            <p className="auth-legal">
              Ao criar um workspace, você receber? dicas de setup e novidades do produto. Voc? pode sair
              quando quiser. Nunca treinamos modelos com seus prompts ou respostas.
            </p>
          </div>
        </section>

        <AuthSidePanel variant="register" />
      </div>
    </div>
  );
}


