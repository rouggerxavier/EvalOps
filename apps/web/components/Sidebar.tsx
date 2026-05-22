"use client";

import type { ElementType } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Database,
  Download,
  FlaskConical,
  Home,
  KeyRound,
  List,
  Sparkles,
  Target,
} from "lucide-react";

import { APP_SHELL_NAV_SECTIONS, projectHref } from "@/components/app-shell-nav";

const NAV_ICONS: Record<string, ElementType> = {
  overview: Home,
  traces: Activity,
  evaluations: Target,
  prompts: Sparkles,
  rubrics: List,
  datasets: Database,
  experiments: FlaskConical,
  keys: KeyRound,
  exports: Download,
};

export function Sidebar({ org, project }: { org: string; project: string }) {
  const pathname = usePathname();
  const base = `/o/${org}/p/${project}`;
  const initials = (project || org).slice(0, 2).toUpperCase();

  function isActive(path: string) {
    if (path === "") return pathname === base || pathname === `${base}/`;
    return pathname.startsWith(base + path);
  }

  return (
    <aside className="sidebar" aria-label="Navegacao principal">
      <Link className="sb-brand" href={base}>
        <span className="sb-brand__logo" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 3.5 L7 1 L12 3.5 L12 10.5 L7 13 L2 10.5 Z" stroke="currentColor" strokeWidth="1.4" />
            <circle cx="7" cy="7" r="1.5" fill="currentColor" />
          </svg>
        </span>
        <span className="sb-brand__name">EvalOps</span>
        <span className="sb-brand__ver">v0.7</span>
      </Link>

      <Link className="sb-workspace" href={base} aria-label="Projeto ativo">
        <span className="sb-workspace__avatar" aria-hidden="true">{initials}</span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span className="sb-workspace__org">Workspace - {org}</span>
          <span className="sb-workspace__proj">{project}</span>
        </span>
      </Link>

      <nav style={{ flex: 1, minHeight: 0 }} aria-label="Secoes do projeto">
        {APP_SHELL_NAV_SECTIONS.map((section) => (
          <section className="sb-section" key={section.label}>
            <div className="sb-section__label">{section.label}</div>
            {section.items.map(({ id, label, path, shortcut }) => {
              const Icon = NAV_ICONS[id] ?? Activity;
              const active = isActive(path);
              return (
                <Link
                  key={id}
                  href={projectHref(base, path)}
                  className={`sb-nav-item${active ? " is-active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  <Icon size={15} aria-hidden="true" />
                  <span>{label}</span>
                  {shortcut ? <span className="sb-nav-item__shortcut">{shortcut}</span> : null}
                </Link>
              );
            })}
          </section>
        ))}
      </nav>

      <div className="sb-footer">
        {/* Status was previously a hardcoded "online — ingestão pronta" string
            even when the API was down. Now it links to /health, which probes
            liveness + readiness in real time. No claim of "online" lives in
            the shell unless that probe confirms it. */}
        <Link href="/health" className="sb-status" prefetch={false}>
          <span style={{ minWidth: 0 }}>
            <span className="sb-status__name">Status do EvalOps</span>
            <span className="sb-status__meta">probes vivos em /health</span>
          </span>
        </Link>
      </div>
    </aside>
  );
}
