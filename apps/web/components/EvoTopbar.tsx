"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { ChevronRight, Menu, Search, X } from "lucide-react";
import { usePathname } from "next/navigation";

import { getActiveNavItem, getPageTitle, projectHref } from "@/components/app-shell-nav";
import { NotificationsBell } from "@/components/ui/NotificationsBell";
import { setEnvironmentAction } from "@/lib/actions";
import { logoutAction } from "@/lib/auth-actions";
import type { NotificationItem } from "@/lib/types";

const ENVIRONMENTS = ["all", "prod", "staging", "dev"] as const;

function envLabel(env: (typeof ENVIRONMENTS)[number]): string {
  if (env === "all") return "Todos os ambientes";
  if (env === "prod") return "Produção";
  if (env === "staging") return "Staging";
  return "Dev";
}

export function EvoTopbar({
  org,
  project,
  orgLabel,
  projectLabel,
  initials,
  notifications = [],
  projectId = null,
  environment = "all",
  mobileMenuOpen,
  onMenuToggle,
}: {
  org: string;
  project: string;
  orgLabel: string;
  projectLabel: string;
  initials: string;
  notifications?: NotificationItem[];
  projectId?: string | null;
  environment?: (typeof ENVIRONMENTS)[number];
  mobileMenuOpen: boolean;
  onMenuToggle: () => void;
}) {
  const pathname = usePathname();
  const base = `/o/${org}/p/${project}`;
  const searchRef = useRef<HTMLInputElement>(null);
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
    <header className="topbar ops-topbar">
      <div className="ops-mobile-brand">
        <strong>EvalOps Studio</strong>
        <button
          type="button"
          className="ops-mobile-menu-toggle"
          onClick={onMenuToggle}
          aria-controls="ops-sidebar"
          aria-label={mobileMenuOpen ? "Fechar menu" : "Abrir menu"}
          aria-expanded={mobileMenuOpen}
        >
          {mobileMenuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
        </button>
      </div>
      <nav className={`crumbs ops-crumbs${isDetailPage ? " ops-crumbs--detail" : ""}`} aria-label="Caminho">
        <span className="ops-crumbs__workspace">{orgLabel}</span>
        <span className="crumbs__sep ops-crumbs__workspace"><ChevronRight size={12} /></span>
        <Link className="ops-crumbs__workspace" href={base}><strong>{projectLabel}</strong></Link>
        <span className="crumbs__sep ops-crumbs__workspace"><ChevronRight size={12} /></span>
        {isDetailPage ? (
          <>
            <Link href={projectHref(base, activeItem.path)}>{activeItem.label}</Link>
            <span className="crumbs__sep"><ChevronRight size={12} /></span>
          </>
        ) : null}
        <strong>{pageName}</strong>
      </nav>

      <form className="topbar__search ops-topbar__search" action={`${base}/traces`} method="get">
        <Search className="topbar__search-icon" size={14} />
        <input ref={searchRef} name="q" placeholder="Buscar por nome, id, usuário ou conversa..." aria-label="Buscar traces" />
        <span className="topbar__search-kbd">CmdK</span>
      </form>

      <div className="topbar__right ops-topbar__right">
        <form action={setEnvironmentAction} className="ops-environment-form">
          <input type="hidden" name="org" value={org} />
          <input type="hidden" name="project" value={project} />
          <input type="hidden" name="current_path" value={pathname ?? `/o/${org}/p/${project}`} />
          <select
            className="filter-select ops-environment-select"
            name="environment"
            aria-label="Ambiente"
            value={environment}
            onChange={(event) => event.currentTarget.form?.requestSubmit()}
          >
            {ENVIRONMENTS.map((env) => <option key={env} value={env}>{envLabel(env)}</option>)}
          </select>
        </form>
        <NotificationsBell
          notifications={notifications}
          org={org}
          project={project}
          projectId={projectId}
          currentPath={pathname ?? `/o/${org}/p/${project}`}
        />

        <form action={logoutAction} className="ops-account-form">
          <button type="submit" className="user-avatar" title="Sair" aria-label="Sair">
            {initials}
          </button>
        </form>
      </div>
    </header>
  );
}
