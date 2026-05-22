"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BookOpen, ChevronRight, Search, Settings } from "lucide-react";
import { usePathname } from "next/navigation";

import { getActiveNavItem, getPageTitle, projectHref } from "@/components/app-shell-nav";
import { NotificationsBell } from "@/components/ui/NotificationsBell";
import { WorkspaceSwitcher } from "@/components/ui/WorkspaceSwitcher";
import { setEnvironmentAction } from "@/lib/actions";
import { logoutAction } from "@/lib/auth-actions";
import type { NotificationItem } from "@/lib/types";

type WorkspaceProject = { org: string; project: string; label: string };

const ENVIRONMENTS = ["prod", "staging", "dev"] as const;

export function EvoTopbar({
  org,
  project,
  initials,
  notifications = [],
  projects = [],
  projectId = null,
  environment = "prod",
}: {
  org: string;
  project: string;
  initials: string;
  notifications?: NotificationItem[];
  projects?: WorkspaceProject[];
  projectId?: string | null;
  environment?: (typeof ENVIRONMENTS)[number];
}) {
  const pathname = usePathname();
  const base = `/o/${org}/p/${project}`;
  const searchRef = useRef<HTMLInputElement>(null);
  const [envOpen, setEnvOpen] = useState(false);
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
                  <form key={env} action={setEnvironmentAction} style={{ margin: 0 }}>
                    <input type="hidden" name="org" value={org} />
                    <input type="hidden" name="project" value={project} />
                    <input type="hidden" name="environment" value={env} />
                    <input
                      type="hidden"
                      name="current_path"
                      value={pathname ?? `/o/${org}/p/${project}`}
                    />
                    <button
                      type="submit"
                      className={`btn btn--sm${env === environment ? " btn--primary" : " btn--ghost"}`}
                      style={{ width: "100%" }}
                    >
                      {env}
                    </button>
                  </form>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {/* Always render the switcher so the "+ Novo projeto…" entry is
            reachable even from accounts with a single project. */}
        <WorkspaceSwitcher current={`${org}/${project}`} projects={projects} />
        <NotificationsBell
          notifications={notifications}
          org={org}
          project={project}
          projectId={projectId}
          currentPath={pathname ?? `/o/${org}/p/${project}`}
        />

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
