"use client";

import type { ElementType } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Activity,
  Database,
  Download,
  FlaskConical,
  LayoutDashboard,
  KeyRound,
  List,
  SlidersHorizontal,
  Sparkles,
  Target,
  X,
} from "lucide-react";

import { APP_SHELL_NAV_SECTIONS, projectHref } from "@/components/app-shell-nav";
import { WorkspaceSwitcher } from "@/components/ui/WorkspaceSwitcher";
import { formatCount } from "@/lib/format";

const NAV_ICONS: Record<string, ElementType> = {
  overview: LayoutDashboard,
  traces: Activity,
  evaluations: Target,
  prompts: Sparkles,
  rubrics: List,
  datasets: Database,
  experiments: FlaskConical,
  keys: KeyRound,
  exports: Download,
  settings: SlidersHorizontal,
};

type WorkspaceProject = { org: string; project: string; label: string };

export function Sidebar({
  org,
  project,
  projects,
  attentionCount,
  usage,
  mobileMenuOpen,
  onNavigate,
  onClose,
}: {
  org: string;
  project: string;
  projects: WorkspaceProject[];
  attentionCount: number | null;
  usage: { used: number; limit: number } | null;
  mobileMenuOpen: boolean;
  onNavigate: () => void;
  onClose: () => void;
}) {
  const pathname = usePathname();
  const queryEnvironment = useSearchParams().get("environment");
  const base = `/o/${org}/p/${project}`;
  const usagePercent = usage?.limit ? Math.min(100, Math.round((usage.used / usage.limit) * 100)) : 0;
  const attentionLabel = attentionCount !== null && attentionCount >= 25 ? "25+" : String(attentionCount ?? "");

  function isActive(path: string) {
    if (path === "") return pathname === base || pathname === `${base}/`;
    return pathname.startsWith(base + path);
  }

  return (
    <aside
      id="ops-sidebar"
      className="sidebar ops-sidebar"
      aria-label="Navegação principal"
      role={mobileMenuOpen ? "dialog" : undefined}
      aria-modal={mobileMenuOpen ? true : undefined}
    >
      <div className="ops-sidebar__head">
        <Link className="sb-brand" href={projectHref(base, "", queryEnvironment)} onClick={onNavigate}>
          <span className="sb-brand__logo" aria-hidden="true">E</span>
          <span className="sb-brand__name">EvalOps Studio</span>
        </Link>
        {mobileMenuOpen ? (
          <button type="button" className="ops-sidebar__close" onClick={onClose} aria-label="Fechar menu">
            <X size={20} aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <div className="ops-sidebar__project">
        <WorkspaceSwitcher current={`${org}/${project}`} projects={projects} />
      </div>

      <nav className="ops-sidebar__nav" aria-label="Seções do projeto">
        {APP_SHELL_NAV_SECTIONS.map((section) => (
          <section className="sb-section" key={section.label}>
            <div className="sb-section__label">{section.label}</div>
            {section.items.map(({ id, label, path, shortcut }) => {
              const Icon = NAV_ICONS[id] ?? Activity;
              const active = isActive(path);
              return (
                <Link
                  key={id}
                  href={projectHref(base, path, queryEnvironment)}
                  className={`sb-nav-item${active ? " is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <Icon size={15} aria-hidden="true" />
                  <span>{label}</span>
                  {id === "overview" && attentionCount !== null && attentionCount > 0 ? (
                    <span
                      className="ops-attention-count"
                      aria-label={`${attentionLabel} traces precisam de atenção nas últimas 24 horas`}
                    >
                      {attentionLabel}
                    </span>
                  ) : shortcut ? <span className="sb-nav-item__shortcut">{shortcut}</span> : null}
                </Link>
              );
            })}
          </section>
        ))}
      </nav>

      <div className="sb-footer ops-sidebar__usage">
        <div className="ops-sidebar__usage-label">
          <span>Traces no mês</span>
          <strong>{usage ? `${usagePercent}%` : "Sem dados"}</strong>
        </div>
        <div
          className="ops-sidebar__usage-track"
          role="progressbar"
          aria-label="Uso mensal de traces"
          aria-valuemin={0}
          aria-valuemax={usage?.limit ?? 100}
          aria-valuenow={usage ? Math.min(usage.used, usage.limit) : 0}
          aria-valuetext={usage ? `${formatCount(usage.used)} de ${formatCount(usage.limit)} traces` : "Sem dados"}
        >
          <span style={{ width: `${usagePercent}%` }} />
        </div>
        <Link className="ops-sidebar__docs" href="/docs" onClick={onNavigate}>Documentação</Link>
      </div>
    </aside>
  );
}
