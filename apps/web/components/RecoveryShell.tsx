import Link from "next/link";
import type { ReactNode } from "react";

export function RecoveryShell({ title, children }: { title: string; children: ReactNode }) {
  return <div className="ops-shell ops-account">
    <main className="ops-account__content">
      <nav className="ops-account__nav" aria-label="Recuperação de senha"><Link href="/login" className="btn btn--ghost">Voltar para entrar</Link></nav>
      <header className="ops-account__heading"><h1>{title}</h1></header>
      <section className="ops-account__password" aria-label={title}>{children}</section>
    </main>
  </div>;
}
