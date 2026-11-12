"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { acceptInvitationAction, type MembershipState } from "@/lib/membership-actions";
import { takeRecoveryFragment } from "@/lib/recovery-fragment";

export function AcceptInvitationForm() {
  const router = useRouter();
  const token = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [state, setState] = useState<MembershipState>({});
  useEffect(() => {
    const capture = () => {
      setReady(false);
      token.current = takeRecoveryFragment(window.location, { state: window.history.state, replaceState: History.prototype.replaceState.bind(window.history) });
      setState(token.current ? {} : { error: "Abra o link completo recebido por email para aceitar o convite." });
      queueMicrotask(() => {
        window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
        setReady(Boolean(token.current));
      });
    };
    if (token.current === null) capture();
    window.addEventListener("hashchange", capture);
    return () => window.removeEventListener("hashchange", capture);
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || !token.current) return;
    const submitted = token.current;
    const form = new FormData();
    form.set("token", submitted);
    setPending(true);
    try {
      const result = await acceptInvitationAction(form);
      if (token.current !== submitted) return;
      if (result.acceptance) { token.current = ""; setReady(false); }
      setState(result);
      if (result.href) router.push(result.href);
    } catch { if (token.current === submitted) setState({ error: "Não foi possível aceitar o convite. Tente novamente." }); }
    finally { setPending(false); }
  }
  return <>
    {!state.acceptance ? <>
      <p>Entre com a conta do email convidado. O acesso só será confirmado ao aceitar o convite.</p>
      <p><Link href="/login" target="_blank" rel="noopener noreferrer">Entrar em outra aba</Link> ou <Link href="/register" target="_blank" rel="noopener noreferrer">criar conta em outra aba</Link>. Depois, volte a esta página ou reabra o link do email.</p>
      <form onSubmit={submit}><button type="submit" className="btn btn--primary" disabled={!ready || pending} aria-busy={pending}>{pending ? "Aceitando…" : "Aceitar convite"}</button></form>
    </> : <div role="status">
      <p>Convite processado para {state.acceptance.organization_slug}. Papel: {state.acceptance.role}.</p>
      {!state.acceptance.permissions.includes("read") ? <p>Seu vínculo foi preservado e o acesso permanece restrito. Solicite ajuda a um owner da organização.</p> : <>
        <p>Acesso confirmado. {state.acceptance.already_member ? "Seu papel existente foi preservado." : ""}</p>
        {state.href ? <Link className="btn btn--primary" href={state.href}>Abrir organização</Link> : <p>{state.success ?? "Esta organização ainda não tem projetos disponíveis."}</p>}
      </>}
    </div>}
    {state.error ? <p role="alert" className="ops-account__error">{state.error}</p> : null}
  </>;
}
