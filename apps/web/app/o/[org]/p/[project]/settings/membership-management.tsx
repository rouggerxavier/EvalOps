"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { loadInvitationsAction, manageMembershipAction, type MembershipState } from "@/lib/membership-actions";
import type { InvitationList, Member } from "@/lib/types";
import styles from "./membership-management.module.css";

type Props = {
  org: string; project: string; organizationId: string; currentUserId: string | null;
  members: Member[]; membersError: string | null; memberCursor: string | null;
  invitations: InvitationList | null; invitationsError: string | null; canAdmin: boolean;
};
const statusLabels = { pending: "Na fila", sending: "Enviando", sent: "Enviado", failed: "Falhou", accepted: "Aceito", revoked: "Revogado", expired: "Expirado" };

export function MembershipManagement({ org, project, organizationId, currentUserId, members, membersError, memberCursor, invitations, invitationsError, canAdmin }: Props) {
  const router = useRouter();
  const [state, setState] = useState<MembershipState>({});
  const [pending, setPending] = useState(false);
  const [adminRevoked, setAdminRevoked] = useState(false);
  const admin = canAdmin && !adminRevoked;
  const [list, setList] = useState(invitations);
  const [confirmation, setConfirmation] = useState<{ operation: "remove" | "transfer"; member: Member } | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const membersTitle = useRef<HTMLHeadingElement>(null);
  const busy = useRef(false);
  useEffect(() => { setList(invitations); }, [invitations]);
  useEffect(() => {
    if (confirmation) { dialog.current?.showModal(); return; }
    // The dialog unmounts instead of close(), so focus is restored by hand.
    const target = opener.current;
    opener.current = null;
    if (target) (target.isConnected ? target : membersTitle.current)?.focus();
  }, [confirmation]);
  function openConfirmation(event: { currentTarget: HTMLElement }, operation: "remove" | "transfer", member: Member) {
    opener.current = event.currentTarget;
    setState({}); setConfirmation({ operation, member });
  }
  function context(form: FormData) {
    form.set("org", org); form.set("project", project); form.set("organization_id", organizationId);
    return form;
  }
  async function mutate(form: FormData) {
    if (busy.current) return;
    busy.current = true; setPending(true); setState({});
    try {
      const result = await manageMembershipAction(context(form));
      setState(result);
      if (!result.error) {
        if (form.get("operation") === "transfer") setAdminRevoked(true);
        // The opener row or button disappears after remove/transfer; land on the list heading.
        if (confirmation) opener.current = membersTitle.current;
        setConfirmation(null);
        if (result.leave) router.replace("/app");
        router.refresh();
      }
    } catch { setState({ error: "Não foi possível confirmar a alteração. Atualize a lista antes de tentar novamente." }); }
    finally { busy.current = false; setPending(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void mutate(new FormData(event.currentTarget));
  }
  async function moreInvitations() {
    if (busy.current || !list?.next_cursor) return;
    busy.current = true; setPending(true);
    try {
      const result = await loadInvitationsAction(organizationId, list.next_cursor);
      if (result.invitations) setList({ data: [...list.data, ...result.invitations.data], next_cursor: result.invitations.next_cursor });
      else setState(result);
    } catch { setState({ error: "Não foi possível carregar os convites. Tente novamente." }); }
    finally { busy.current = false; setPending(false); }
  }
  const message = <>{state.error ? <p role="alert" className="ops-note">{state.error}</p> : null}{state.success ? <p role="status" className="ops-note">{state.success}</p> : null}</>;
  return <div className={`ops-stack ${styles.root}`}>
    {!confirmation ? message : null}
    {admin ? <section className="card">
      <div className="card__header"><h2 className="card__title">Convidar pessoa</h2></div>
      <form className="ops-form" onSubmit={submit} aria-busy={pending}>
        <input type="hidden" name="operation" value="invite" />
        <label className="ops-form__field"><span>Email do convite</span><input name="email" type="email" autoComplete="email" required maxLength={320} disabled={pending} /></label>
        <label className="ops-form__field"><span>Papel do convite</span><select name="role" defaultValue="viewer" disabled={pending}><option value="viewer">Viewer — leitura</option><option value="member">Member — leitura e escrita</option></select></label>
        <button className="btn btn--primary" type="submit" disabled={pending}>{pending ? "Aguarde…" : "Enviar convite"}</button>
      </form>
      <p className="ops-note">O convite expira em 24 horas. Emitir novamente invalida os links anteriores para o mesmo email.</p>
    </section> : <p className="ops-note">Acesso de {admin ? "administração" : "consulta"}. Somente um owner pode administrar membros, convites e configurações.</p>}
    <section className="card">
      <div className="card__header"><h2 className="card__title" ref={membersTitle} tabIndex={-1}>Membros</h2></div>
      {membersError ? <p role="alert" className="ops-empty">{membersError}</p> : <div className="table-wrap"><table className="t">
        <thead><tr><th>Nome e email</th><th>Papel</th><th>Entrou</th>{admin ? <th>Ações</th> : null}</tr></thead>
        <tbody>{members.length === 0 ? <tr><td colSpan={admin ? 4 : 3}>Sem membros nesta página.</td></tr> : members.map((member) => <tr key={member.user_id}>
          <td><strong>{member.name || "Sem nome"}</strong><br />{member.email}{member.user_id === currentUserId ? " (você)" : ""}</td>
          <td>{member.role}</td>
          <td><time dateTime={member.joined_at}>{new Date(member.joined_at).toLocaleDateString("pt-BR", { timeZone: "UTC" })}</time></td>
          {admin ? <td><div className={styles.actions}>
            {member.role !== "owner" ? <form onSubmit={submit} className={styles.actions}>
              <input type="hidden" name="operation" value="role" /><input type="hidden" name="target" value={member.user_id} />
              {/* Owners change only through transfer; unknown roles never get an implicit PATCH. */}
              <select name="role" required defaultValue={member.role === "member" || member.role === "viewer" ? member.role : ""} aria-label={`Novo papel de ${member.email}`} disabled={pending}>
                {member.role !== "member" && member.role !== "viewer" ? <option value="" disabled>Manter papel atual ({member.role})</option> : null}
                <option value="viewer">Viewer</option><option value="member">Member</option>
              </select>
              <button type="submit" className="btn btn--sm" disabled={pending}>Salvar papel</button>
            </form> : null}
            <button type="button" className="btn btn--sm" disabled={pending} aria-label={`Remover ${member.email}`} onClick={(event) => openConfirmation(event, "remove", member)}>Remover</button>
            {member.user_id !== currentUserId && (member.role === "member" || member.role === "viewer") ? <button type="button" className="btn btn--sm" disabled={pending} aria-label={`Transferir para ${member.email}`} onClick={(event) => openConfirmation(event, "transfer", member)}>Transferir propriedade</button> : null}
          </div></td> : null}
        </tr>)}</tbody>
      </table></div>}
      {memberCursor ? <a className="btn" href={`?member_cursor=${encodeURIComponent(memberCursor)}`}>Próxima página de membros</a> : null}
    </section>
    {admin ? <section className="card">
      <div className="card__header"><h2 className="card__title">Convites</h2><button type="button" className="btn btn--sm" disabled={pending} onClick={() => router.refresh()}>Atualizar lista</button></div>
      {invitationsError ? <p role="alert" className="ops-empty">{invitationsError}</p> : <div className="table-wrap"><table className="t">
        <thead><tr><th>Email e papel</th><th>Estado</th><th>Prazo</th><th>Ações</th></tr></thead>
        <tbody>{!list?.data.length ? <tr><td colSpan={4}>Nenhum convite nesta organização.</td></tr> : list.data.map((invitation) => <tr key={invitation.id}>
          <td>{invitation.email}<br />{invitation.role}</td><td>{statusLabels[invitation.status]}</td><td><time dateTime={invitation.expires_at}>{new Date(invitation.expires_at).toLocaleString("pt-BR", { timeZone: "UTC" })} UTC</time></td>
          <td><div className={styles.actions}>
            {["pending", "sending", "sent"].includes(invitation.status) ? <form onSubmit={submit}><input type="hidden" name="operation" value="revoke" /><input type="hidden" name="target" value={invitation.id} /><button type="submit" className="btn btn--sm" disabled={pending} aria-label={`Revogar convite de ${invitation.email}`}>Revogar</button></form> : null}
            {invitation.status !== "accepted" ? <form onSubmit={submit}><input type="hidden" name="operation" value="invite" /><input type="hidden" name="email" value={invitation.email} /><input type="hidden" name="role" value={invitation.role} /><button type="submit" className="btn btn--sm" disabled={pending} aria-label={`Emitir novamente para ${invitation.email}`}>Emitir novamente</button></form> : null}
          </div></td>
        </tr>)}</tbody>
      </table></div>}
      {list?.next_cursor ? <button type="button" className="btn" disabled={pending} onClick={moreInvitations}>Carregar mais convites</button> : null}
    </section> : null}
    {confirmation ? <dialog ref={dialog} className={styles.dialog} aria-labelledby="membership-confirm-title" onCancel={(event) => { if (pending) event.preventDefault(); else setConfirmation(null); }}>
      <h2 id="membership-confirm-title">{confirmation.operation === "remove" ? "Remover membro?" : "Transferir propriedade?"}</h2>
      <p>{confirmation.member.email}</p>
      <p>{confirmation.operation === "remove" ? "Esta pessoa perderá o acesso à organização. Convites ativos para o email dela serão revogados." : "Esta pessoa será owner e você passará a member, perdendo acesso à administração."}</p>
      {message}
      <form onSubmit={submit} aria-busy={pending}>
        <input type="hidden" name="operation" value={confirmation.operation} /><input type="hidden" name="target" value={confirmation.member.user_id} /><input type="hidden" name="confirmed" value="yes" />
        <div className={styles.actions}><button type="button" className="btn" autoFocus disabled={pending} onClick={() => setConfirmation(null)}>Cancelar</button><button type="submit" className="btn btn--primary" disabled={pending}>{pending ? "Aguarde…" : confirmation.operation === "remove" ? "Confirmar remoção" : "Confirmar transferência"}</button></div>
      </form>
    </dialog> : null}
  </div>;
}
