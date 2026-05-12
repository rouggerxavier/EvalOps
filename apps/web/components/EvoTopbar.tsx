"use client";

import Link from "next/link";
import { Bell, BookOpen, ChevronRight, Search } from "lucide-react";
import { usePathname } from "next/navigation";

import { logoutAction } from "@/lib/auth-actions";

const PAGE_NAMES: Record<string, string> = {
  "":             "Visão geral",
  "/traces":      "Traces",
  "/evaluations": "Avaliações",
  "/experiments": "Experimentos",
  "/prompts":     "Prompts",
  "/rubrics":     "Rubricas",
  "/datasets":    "Datasets",
  "/keys":        "Chaves API",
  "/exports":     "Exports",
};

function getPageName(pathname: string, base: string): string {
  const sub = pathname.slice(base.length).replace(/\/$/, "");
  const segment = Object.keys(PAGE_NAMES)
    .filter((k) => sub === k || sub.startsWith(k + "/"))
    .sort((a, b) => b.length - a.length)[0];
  return PAGE_NAMES[segment ?? ""] ?? sub;
}

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
  const pageName = getPageName(pathname, base);

  return (
    <header className="evo-topbar">
      <div className="evo-breadcrumbs">
        <span className="evo-breadcrumbs__seg">{org}</span>
        <span className="evo-breadcrumbs__sep">
          <ChevronRight size={12} />
        </span>
        <span className="evo-breadcrumbs__seg">{project}</span>
        <span className="evo-breadcrumbs__sep">
          <ChevronRight size={12} />
        </span>
        <span className="evo-breadcrumbs__current">{pageName}</span>
      </div>

      <form className="evo-search" action={`/o/${org}/p/${project}/traces`} method="get">
        <Search size={14} />
        <input name="name" placeholder="Buscar traces, prompts, rubricas..." />
        <span className="evo-search__kbd">/</span>
      </form>

      <div className="evo-topbar__divider" />
      <Link className="evo-topbar__action" href="/docs" aria-label="Documentação">
        <BookOpen size={16} />
      </Link>
      <button
        type="button"
        className="evo-topbar__action evo-topbar__action--dot"
        aria-label="Notificações"
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
