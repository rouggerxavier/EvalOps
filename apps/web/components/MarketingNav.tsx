import Link from "next/link";
import { ArrowRight } from "lucide-react";

type Props = {
  variant?: "landing" | "default";
};

export function MarketingNav({ variant = "default" }: Props) {
  return (
    <header className="mk-nav">
      <Link href="/" className="mk-brand">
        <img src="/brand/mark-evalops.svg" alt="" />
        <span>
          EvalOps<span className="sub">Studio</span>
        </span>
      </Link>
      {variant === "landing" ? (
        <nav className="mk-nav__links">
          <a href="#product">Produto</a>
          <a href="#how">Como funciona</a>
          <a href="#sdk">SDK</a>
          <Link href="/docs">Documentação</Link>
          <Link href="/changelog">Changelog</Link>
        </nav>
      ) : (
        <nav className="mk-nav__links">
          <Link href="/docs">Documentação</Link>
          <Link href="/changelog">Changelog</Link>
        </nav>
      )}
      <span className="mk-nav__spacer" />
      <div className="mk-nav__actions">
        <Link className="mk-btn mk-btn--ghost" href="/login">
          Entrar
        </Link>
        <Link className="mk-btn mk-btn--primary" href="/register">
          Abrir dashboard
          <ArrowRight />
        </Link>
      </div>
    </header>
  );
}
