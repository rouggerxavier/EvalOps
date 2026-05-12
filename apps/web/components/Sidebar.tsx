"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ChevronDown,
  Database,
  Download,
  FlaskConical,
  Home,
  KeyRound,
  List,
  Sparkles,
  Target,
} from "lucide-react";

type NavItem = {
  id: string;
  label: string;
  Icon: React.ElementType;
  path: string;
  shortcut?: string;
};

const SECTIONS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Projeto",
    items: [
      { id: "overview",    label: "Visão geral", Icon: Home,         path: "",             shortcut: "G O" },
      { id: "traces",      label: "Traces",       Icon: Activity,     path: "/traces",      shortcut: "G T" },
      { id: "evaluations", label: "Avaliações",   Icon: Target,       path: "/evaluations", shortcut: "G E" },
      { id: "experiments", label: "Experimentos", Icon: FlaskConical, path: "/experiments", shortcut: "G X" },
    ],
  },
  {
    label: "Recursos",
    items: [
      { id: "prompts",  label: "Prompts",  Icon: Sparkles, path: "/prompts" },
      { id: "rubrics",  label: "Rubricas", Icon: List,     path: "/rubrics" },
      { id: "datasets", label: "Datasets", Icon: Database, path: "/datasets" },
    ],
  },
  {
    label: "Operação",
    items: [
      { id: "keys",    label: "Chaves API", Icon: KeyRound, path: "/keys" },
      { id: "exports", label: "Exports",    Icon: Download, path: "/exports" },
    ],
  },
];

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
        <div className="evo-sidebar__brand-name">EvalOps</div>
        <span className="evo-sidebar__brand-meta">v1.0</span>
      </div>

      <div className="evo-project-switcher">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="evo-project-switcher__org">{org} · prod</div>
          <div className="evo-project-switcher__name">{project}</div>
        </div>
        <ChevronDown size={14} className="evo-project-switcher__chevron" />
      </div>

      {SECTIONS.map((section) => (
        <div className="evo-nav-section" key={section.label}>
          <div className="evo-nav-section__label">{section.label}</div>
          {section.items.map(({ id, label, Icon, path, shortcut }) => (
            <Link
              key={id}
              href={path === "" ? base : `${base}${path}`}
              className={`evo-nav-item${isActive(path) ? " is-active" : ""}`}
            >
              <Icon className="evo-nav-item__icon" size={15} />
              <span>{label}</span>
              {shortcut ? <span className="evo-nav-item__shortcut">{shortcut}</span> : null}
            </Link>
          ))}
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
