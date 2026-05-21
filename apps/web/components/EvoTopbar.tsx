"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, BookOpen, ChevronRight, Search, Settings } from "lucide-react";
import { usePathname } from "next/navigation";

import { getActiveNavItem, getPageTitle, projectHref } from "@/components/app-shell-nav";
import { logoutAction } from "@/lib/auth-actions";

const ENVIRONMENTS = ["prod", "staging", "dev"] as const;

export function EvoTopbar({
  org,
  project,
  initials,
}: {
  org: string;
  project: string;
  initials: string;
}) {
  const pathname = usePathname();
  const base = `/o/${org}/p/${project}`;
  const searchRef = useRef<HTMLInputElement>(null);
  const [environment, setEnvironment] = useState<(typeof ENVIRONMENTS)[number]>("prod");
  const [envOpen, setEnvOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const activeItem = getActiveNavItem(pathname, base);
  const pageName = getPageTitle(pathname, base);
  const isDetailPage = pageName !== activeItem.label;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName.toLowerCase();
      const isEditable = target?.isContentEditable || tagName === "input" || tagName === "textarea" || tagName === "select";
      const wantsSearch = event.key === "/" || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k");

      if (!wantsSearch || isEditable) return;

      event.preventDefault();
      searchRef.current?.focus();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <header className="topbar">
      <nav className="crumbs" aria-label="Breadcrumb">
        <span>{org}</span>
        <span className="crumbs__sep"><ChevronRight size={12} /></span>
        <Link href={base}><strong>{project}</strong></Link>
        <span className="crumbs__sep"><ChevronRight size={12} /></span>
        {isDetailPage ? (
          <>
            <Link href={projectHref(base, activeItem.path)}>{activeItem.label}</Link>
            <span className="crumbs__sep"><ChevronRight size={12} /></span>
          </>
        ) : null}
        <strong>{pageName}</strong>
      </nav>

      <form className="topbar__search" action={`${base}/traces`} method="get">
        <Search className="topbar__search-icon" size={14} />
        <input ref={searchRef} name="name" placeholder="Buscar traces por nome..." />
        <span className="topbar__search-kbd">CmdK</span>
      </form>

      <div className="topbar__right">
        <div style={{ position: "relative" }}>
          <button
            type="button"
            className="env-chip"
            onClick={() => setEnvOpen((value) => !value)}
            aria-expanded={envOpen}
            aria-label="Ambiente ativo"
          >
            <span className="env-chip__dot" aria-hidden="true" />
            {environment}
          </button>
          {envOpen ? (
            <div className="card" style={{ position: "absolute", right: 0, top: 34, width: 148, zIndex: 20 }}>
              <div className="card__body" style={{ display: "grid", gap: 6, padding: 8 }}>
                {ENVIRONMENTS.map((env) => (
                  <button
                    key={env}
                    type="button"
                    className={`btn btn--sm${env === environment ? " btn--primary" : " btn--ghost"}`}
                    onClick={() => {
                      setEnvironment(env);
                      setEnvOpen(false);
                    }}
                  >
                    {env}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        <button
          type="button"
          className="icon-btn"
          onClick={() => setNotificationsOpen((value) => !value)}
          aria-label="Notificacoes"
          aria-expanded={notificationsOpen}
        >
          <Bell size={15} />
        </button>
        {notificationsOpen ? (
          <div className="card" style={{ position: "absolute", right: 74, top: 42, width: 300, zIndex: 20 }}>
            <div className="card__header">
              <h3 className="card__title">Notificacoes</h3>
            </div>
            <div className="card__body">
              <div className="faint">Sem notificacoes novas.</div>
            </div>
          </div>
        ) : null}

        <Link className="icon-btn" href="/docs" aria-label="Documentacao">
          <BookOpen size={15} />
        </Link>
        <Link className="icon-btn" href={`${base}/settings`} aria-label="Settings">
          <Settings size={15} />
        </Link>
        <form action={logoutAction} style={{ display: "inline-flex" }}>
          <button type="submit" className="user-avatar" title="Sair" aria-label="Sair">
            {initials}
          </button>
        </form>
      </div>
    </header>
  );
}
