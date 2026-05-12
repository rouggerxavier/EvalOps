"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, Menu, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Props = {
  variant?: "landing" | "default";
};

type NavItem = {
  href: string;
  label: string;
  kind: "route" | "anchor";
};

const LANDING_ITEMS: NavItem[] = [
  { href: "#product", label: "Produto", kind: "anchor" },
  { href: "#how", label: "Como funciona", kind: "anchor" },
  { href: "#sdk", label: "SDK", kind: "anchor" },
  { href: "/docs", label: "Documentação", kind: "route" },
  { href: "/changelog", label: "Changelog", kind: "route" },
];

const DEFAULT_ITEMS: NavItem[] = [
  { href: "/docs", label: "Documentação", kind: "route" },
  { href: "/changelog", label: "Changelog", kind: "route" },
];

function isActive(item: NavItem, pathname: string, hash: string) {
  if (item.kind === "anchor") {
    return pathname === "/" && hash === item.href;
  }

  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

export function MarketingNav({ variant = "default" }: Props) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hash, setHash] = useState("");

  const navItems = useMemo(() => {
    return variant === "landing" ? LANDING_ITEMS : DEFAULT_ITEMS;
  }, [variant]);

  useEffect(() => {
    const syncHash = () => {
      setHash(window.location.hash || "");
    };

    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname, hash]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [menuOpen]);

  const renderNavItem = (item: NavItem, onNavigate?: () => void) => {
    const active = isActive(item, pathname, hash);
    const className = active ? "is-active" : undefined;
    const ariaCurrent = active ? "page" : undefined;

    if (item.kind === "route") {
      return (
        <Link
          key={item.href}
          href={item.href}
          className={className}
          aria-current={ariaCurrent}
          onClick={onNavigate}
        >
          {item.label}
        </Link>
      );
    }

    return (
      <a key={item.href} href={item.href} className={className} aria-current={ariaCurrent} onClick={onNavigate}>
        {item.label}
      </a>
    );
  };

  return (
    <header className={`mk-nav${menuOpen ? " is-open" : ""}`}>
      <div className="mk-nav__row">
        <Link href="/" className="mk-brand">
          <img src="/brand/mark-evalops.svg" alt="" />
          <span>
            EvalOps<span className="sub">Studio</span>
          </span>
        </Link>

        <nav className="mk-nav__links" aria-label="Navegação principal">
          {navItems.map((item) => renderNavItem(item))}
        </nav>

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

        <button
          type="button"
          className="mk-nav__menu-btn"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-controls="mk-mobile-menu"
          aria-label={menuOpen ? "Fechar menu" : "Abrir menu"}
        >
          {menuOpen ? <X /> : <Menu />}
        </button>
      </div>

      <div className="mk-nav__mobile" id="mk-mobile-menu" aria-hidden={!menuOpen}>
        <nav className="mk-nav__mobile-links" aria-label="Navegação mobile">
          {navItems.map((item) => renderNavItem(item, () => setMenuOpen(false)))}
        </nav>
        <div className="mk-nav__mobile-actions">
          <Link className="mk-btn mk-btn--ghost mk-btn--block" href="/login" onClick={() => setMenuOpen(false)}>
            Entrar
          </Link>
          <Link className="mk-btn mk-btn--primary mk-btn--block" href="/register" onClick={() => setMenuOpen(false)}>
            Abrir dashboard
            <ArrowRight />
          </Link>
        </div>
      </div>
    </header>
  );
}

