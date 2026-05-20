"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { Bell, BookOpen, ChevronRight, Search } from "lucide-react";
import { usePathname } from "next/navigation";

import { getActiveNavItem, getPageTitle, projectHref } from "@/components/app-shell-nav";
import { logoutAction } from "@/lib/auth-actions";

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
    <header className="evo-topbar">
      <div className="evo-topbar__context">
        <div className="evo-topbar__eyebrow">Workspace · {org}</div>
        <div className="evo-breadcrumbs" aria-label="Breadcrumb">
          <Link className="evo-breadcrumbs__seg" href={base}>{project}</Link>
          <span className="evo-breadcrumbs__sep">
            <ChevronRight size={12} />
          </span>
          {isDetailPage ? (
            <>
              <Link className="evo-breadcrumbs__seg" href={projectHref(base, activeItem.path)}>{activeItem.label}</Link>
              <span className="evo-breadcrumbs__sep">
                <ChevronRight size={12} />
              </span>
            </>
          ) : null}
          <span className="evo-breadcrumbs__current">{pageName}</span>
        </div>
      </div>

      <form className="evo-search" action={`/o/${org}/p/${project}/traces`} method="get">
        <Search size={14} />
        <input ref={searchRef} name="name" placeholder="Buscar traces por nome..." />
        <span className="evo-search__kbd">⌘K</span>
      </form>

      <div className="evo-env-pill" aria-label="Ambiente ativo">
        <span className="evo-env-pill__dot" aria-hidden="true" />
        env: prod
      </div>
      <div className="evo-topbar__divider" />
      <Link className="evo-topbar__action" href="/docs" aria-label="Documentação">
        <BookOpen size={16} />
      </Link>
      <button
        type="button"
        className="evo-topbar__action"
        aria-label="Alertas planejados"
        title="Alertas planejados"
        data-status="planned"
        disabled
      >
        <Bell size={16} />
      </button>
      <form action={logoutAction} style={{ display: "inline-flex", alignItems: "center" }}>
        <button
          type="submit"
          className="evo-user-avatar"
          title="Sair"
          aria-label="Sair"
          style={{ cursor: "pointer", border: "none", background: "none", padding: 0 }}
        >
          {initials}
        </button>
      </form>
    </header>
  );
}
