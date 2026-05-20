"use client";

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

const NAV_ICONS: Record<string, React.ElementType> = {
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

  function isActive(path: string) {
    if (path === "") return pathname === base || pathname === base + "/";
    return pathname.startsWith(base + path);
  }

  return (
    <aside className="evo-sidebar">
      <div className="evo-sidebar__brand">
        <div className="evo-sidebar__logo" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 3.5 L7 1 L12 3.5 L12 10.5 L7 13 L2 10.5 Z" stroke="#4F8CFF" strokeWidth="1.4" />
            <circle cx="7" cy="7" r="1.5" fill="#4F8CFF" />
          </svg>
        </div>
        <div className="evo-sidebar__brand-text">
          <div className="evo-sidebar__brand-name">EvalOps</div>
          <div className="evo-sidebar__brand-kicker">Project cockpit</div>
        </div>
      </div>

      <div className="evo-project-context" aria-label="Contexto do projeto ativo">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="evo-project-context__eyebrow">Workspace · {org}</div>
          <div className="evo-project-context__name">{project}</div>
        </div>
        <span className="evo-context-pill">
          <span className="evo-context-pill__dot" aria-hidden="true" />
          prod
        </span>
      </div>

      {APP_SHELL_NAV_SECTIONS.map((section) => (
        <div className="evo-nav-section" key={section.label}>
          <div className="evo-nav-section__label">{section.label}</div>
          {section.items.map(({ id, label, path, shortcut }) => {
            const Icon = NAV_ICONS[id];
            const active = isActive(path);
            return (
              <Link
                key={id}
                href={projectHref(base, path)}
                className={`evo-nav-item${active ? " is-active" : ""}`}
                aria-current={active ? "page" : undefined}
              >
                <Icon className="evo-nav-item__icon" size={15} />
                <span className="evo-nav-item__label">{label}</span>
                {shortcut ? <span className="evo-nav-item__shortcut">{shortcut}</span> : null}
              </Link>
            );
          })}
        </div>
      ))}

      <div className="evo-sidebar__footer">
        <div className="evo-sdk-status">
          <span className="evo-pulse" aria-hidden="true" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="evo-sdk-status__name">SDK Python</div>
            <div className="evo-sdk-status__meta">online · ingestão pronta</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
