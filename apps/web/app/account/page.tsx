import Link from "next/link";
import { redirect } from "next/navigation";

import { ChangePasswordSubmit } from "@/components/ChangePasswordSubmit";
import { getSession } from "@/lib/auth";
import { changePasswordAction, logoutAction } from "@/lib/auth-actions";

export const metadata = { title: "Conta - EvalOps Studio" };
export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  invalid_password: "Informe a senha atual e uma nova senha de 8 a 256 caracteres.",
  password_mismatch: "A confirmação não corresponde à nova senha. Digite as duas novamente.",
  invalid_current_password: "Senha atual incorreta. Confira e tente novamente.",
  too_many_attempts: "Muitas tentativas. Aguarde 5 minutos antes de tentar novamente.",
  unavailable: "Não foi possível confirmar a troca. Tente entrar com a nova senha antes de repetir.",
};

export default async function AccountPage({ searchParams }: {
  searchParams: Promise<{ error?: string }>;
}) {
  const session = await getSession();
  if (!session) redirect("/login");
  const { error } = await searchParams;
  const message = error ? (Object.hasOwn(ERRORS, error) ? ERRORS[error] : ERRORS.unavailable) : null;

  const invalidCurrent = error === "invalid_current_password" || error === "invalid_password";
  const invalidNew = error === "invalid_password" || error === "password_mismatch";
  const invalidConfirmation = error === "password_mismatch";

  return (
    <div className="ops-shell ops-account">
      <main className="ops-account__content">
        <nav className="ops-account__nav" aria-label="Conta">
          <Link href="/app" className="btn btn--ghost">Voltar ao workspace</Link>
          <form action={logoutAction}><button className="btn" type="submit">Sair</button></form>
        </nav>
        <header className="ops-account__heading">
          <h1>Conta</h1>
          <p>{session.user.email}</p>
        </header>
        <section className="ops-account__password" aria-labelledby="password-heading">
          <h2 id="password-heading">Trocar senha</h2>
          <p id="password-impact">Ao trocar a senha, todas as suas sessões serão encerradas, inclusive esta. Você precisará entrar novamente.</p>
          {message ? <p id="password-error" className="ops-account__error" role="alert">{message}</p> : null}
          <form action={changePasswordAction} aria-describedby="password-impact">
            <div className="auth-field">
              <label htmlFor="current-password">Senha atual</label>
              <input id="current-password" name="current_password" type="password" autoComplete="current-password" aria-invalid={invalidCurrent || undefined} aria-describedby={invalidCurrent ? "password-error" : undefined} required />
            </div>
            <div className="auth-field">
              <label htmlFor="new-password">Nova senha</label>
              <input id="new-password" name="new_password" type="password" autoComplete="new-password" aria-invalid={invalidNew || undefined} aria-describedby={invalidNew ? "password-policy password-error" : "password-policy"} required />
              <span id="password-policy">Use de 8 a 256 caracteres.</span>
            </div>
            <div className="auth-field">
              <label htmlFor="confirm-password">Confirmar nova senha</label>
              <input id="confirm-password" name="confirm_password" type="password" autoComplete="new-password" aria-invalid={invalidConfirmation || undefined} aria-describedby={invalidConfirmation ? "password-error" : undefined} required />
            </div>
            <ChangePasswordSubmit />
          </form>
        </section>
      </main>
    </div>
  );
}
