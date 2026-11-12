"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useFormState, useFormStatus } from "react-dom";
import { forgotPasswordAction, resetPasswordAction, type RecoveryState } from "@/lib/recovery-actions";
import { takeRecoveryFragment } from "@/lib/recovery-fragment";

function errorMessage(code: string): string {
  switch (code) {
    case "invalid_email": return "Informe um email válido.";
    case "invalid_reset": return "Este link é inválido, expirou ou já foi usado. Peça um novo link.";
    case "invalid_password": return "Use uma senha de 8 a 256 caracteres.";
    case "password_mismatch": return "A confirmação deve ser igual à nova senha.";
    case "too_many_attempts": return "Muitas tentativas. Aguarde alguns minutos e tente novamente.";
    default: return "A recuperação de senha está indisponível no momento. Tente novamente mais tarde ou entre em contato com o administrador.";
  }
}

function RecoverySubmit() {
  const { pending } = useFormStatus();
  return <button className="btn btn--primary" type="submit" disabled={pending} aria-busy={pending}>{pending ? "Enviando…" : "Enviar link de recuperação"}</button>;
}

export function ForgotPasswordForm() {
  const [state, action] = useFormState(forgotPasswordAction, {});
  return <>
    <p id="recovery-description">Informe o email da sua conta para receber um link de recuperação.</p>
    {state.sent ? <p role="status">Se existir uma conta com senha para este email, você receberá um link. Confira também a pasta de spam.</p> : null}
    {state.error ? <p id="recovery-error" className="ops-account__error" role="alert">{errorMessage(state.error)}</p> : null}
    <form action={action} aria-describedby="recovery-description">
      <div className="auth-field"><label htmlFor="recovery-email">Email</label>
        <input id="recovery-email" name="email" type="email" autoComplete="email" required maxLength={320} aria-invalid={state.error === "invalid_email" || undefined} aria-describedby={state.error === "invalid_email" ? "recovery-error" : undefined} />
      </div>
      <RecoverySubmit />
    </form>
  </>;
}

export function ResetPasswordForm() {
  const token = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<RecoveryState>({});
  useEffect(() => {
    const capture = () => {
      setReady(false);
      // Use the native method so a hash-only entry with null state stays null.
      token.current = takeRecoveryFragment(window.location, {
        state: window.history.state, replaceState: History.prototype.replaceState.bind(window.history),
      });
      setState(token.current ? {} : { error: "invalid_reset" });
      // Let the router restore the cleaned history after its hydration listeners are installed.
      queueMicrotask(() => {
        window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
        setReady(Boolean(token.current));
      });
    };
    // StrictMode re-runs effects after the fragment was already consumed.
    if (token.current === null) capture();
    window.addEventListener("hashchange", capture);
    return () => window.removeEventListener("hashchange", capture);
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending || !token.current) return;
    const submittedToken = token.current;
    const form = new FormData(event.currentTarget);
    form.set("token", submittedToken);
    setPending(true);
    try {
      const result = await resetPasswordAction(form);
      if (token.current === submittedToken) setState(result);
    }
    catch { if (token.current === submittedToken) setState({ error: "unavailable" }); }
    finally { setPending(false); }
  }
  const invalidPassword = state.error === "invalid_password" || state.error === "password_mismatch";
  return <>
    <p id="reset-impact">Use de 8 a 256 caracteres. Ao redefinir a senha, todas as suas sessões serão encerradas. Você precisará entrar novamente.</p>
    {state.error ? <p id="recovery-error" className="ops-account__error" role="alert">{errorMessage(state.error)} {state.error === "invalid_reset" ? <Link href="/forgot-password">Pedir novo link</Link> : null}</p> : null}
    <form onSubmit={submit} aria-describedby="reset-impact">
      <div className="auth-field"><label htmlFor="reset-password">Nova senha</label>
        <input id="reset-password" name="new_password" type="password" autoComplete="new-password" required disabled={!ready} aria-invalid={invalidPassword || undefined} aria-describedby={invalidPassword ? "reset-impact recovery-error" : "reset-impact"} />
      </div>
      <div className="auth-field"><label htmlFor="reset-confirmation">Confirmar nova senha</label>
        <input id="reset-confirmation" name="confirm_password" type="password" autoComplete="new-password" required disabled={!ready} aria-invalid={state.error === "password_mismatch" || undefined} aria-describedby={state.error === "password_mismatch" ? "recovery-error" : undefined} />
      </div>
      <button className="btn btn--primary" type="submit" disabled={!ready || pending} aria-busy={pending}>{pending ? "Redefinindo…" : "Redefinir senha e entrar"}</button>
    </form>
  </>;
}
