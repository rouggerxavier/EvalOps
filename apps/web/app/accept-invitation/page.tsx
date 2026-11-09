import Link from "next/link";
import { AcceptInvitationForm } from "./invitation-form";

export const metadata = { title: "Aceitar convite - EvalOps Studio", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function AcceptInvitationPage() {
  return <div className="ops-shell ops-account"><main className="ops-account__content">
    <nav className="ops-account__nav" aria-label="Convite"><Link href="/app" className="btn btn--ghost">Voltar ao app</Link></nav>
    <header className="ops-account__heading"><h1>Aceitar convite</h1></header>
    <section className="ops-account__password" aria-label="Convite para organização"><AcceptInvitationForm /></section>
  </main></div>;
}
