"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Activity,
  Gauge,
  ListChecks,
  FileText,
  Database,
  FlaskConical,
  GitCompare,
  Download,
  KeyRound,
  Settings,
  ChevronsUpDown,
  Terminal,
} from "lucide-react";

const ACTIVE_NAV = [
  { id: "overview",   label: "Overview",    Icon: LayoutDashboard, path: "" },
  { id: "traces",     label: "Traces",      Icon: Activity,        path: "/traces" },
  { id: "evals",      label: "Evaluations", Icon: Gauge,           path: "/evaluations" },
  { id: "rubrics",    label: "Rubrics",     Icon: ListChecks,      path: "/rubrics" },
  { id: "keys",       label: "API Keys",    Icon: KeyRound,        path: "/keys" },
  { id: "prompts",    label: "Prompts",     Icon: FileText,        path: "/prompts" },
  { id: "datasets",   label: "Datasets",    Icon: Database,        path: "/datasets" },
  { id: "experiments",label: "Experiments", Icon: FlaskConical,    path: "/experiments" },
  { id: "exports",    label: "Exports",     Icon: Download,         path: "/exports" },
];

const FUTURE_NAV = [
  { id: "regression", label: "Regression",  Icon: GitCompare },
  { id: "settings",   label: "Settings",    Icon: Settings,        path: "/settings" },
];

export function Sidebar({ org, project }: { org: string; project: string }) {
  const pathname = usePathname();
  const base = `/o/${org}/p/${project}`;

  function isActive(path: string) {
    if (path === "") return pathname === base || pathname === base + "/";
    return pathname.startsWith(base + path);
  }

  const initials = org.substring(0, 2).toUpperCase();

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <svg className="mark" width="22" height="22" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <circle cx="16" cy="16" r="13" stroke="#3b8df5" strokeWidth="2" />
          <circle cx="16" cy="16" r="7" stroke="#22d3ee" strokeWidth="2" />
          <circle cx="16" cy="16" r="2.5" fill="#22d3ee" />
        </svg>
        <div className="name">
          EvalOps<span className="sub">Studio</span>
        </div>
      </div>

      <div className="workspace">
        <div className="workspace__avatar">{initials}</div>
        <div className="workspace__meta">
          <span className="workspace__label">Workspace</span>
          <span className="workspace__name">{org}</span>
        </div>
        <ChevronsUpDown size={14} className="workspace__chevron" />
      </div>

      <nav className="nav">
        <div className="nav__group-label">Live now</div>
        {ACTIVE_NAV.map(({ id, label, Icon, path }) => (
          <Link
            key={id}
            href={path === "" ? base : `${base}${path}`}
            className={`nav__item${isActive(path) ? " active" : ""}`}
          >
            <Icon size={16} />
            <span>{label}</span>
          </Link>
        ))}

        <div className="nav__group-label" style={{ marginTop: 10 }}>Future</div>
        {FUTURE_NAV.map(({ id, label, Icon }) => (
          <div key={id} className="nav__item nav__item--disabled" aria-disabled="true">
            <Icon size={16} />
            <span>{label}</span>
            <span className="nav__tag">Soon</span>
          </div>
        ))}
      </nav>

      <div className="sidebar__footer">
        <div className="side-card">
          <div className="side-card__row">
            <div className="side-card__icon">
              <KeyRound size={14} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="side-card__title">API Keys</div>
              <div className="side-card__meta">Project access management</div>
            </div>
          </div>
        </div>

        <div className="side-card">
          <div className="side-card__row">
            <div
              className="side-card__icon"
              style={{ background: "rgba(46,194,126,0.14)", color: "var(--success)" }}
            >
              <Terminal size={14} />
            </div>
            <div style={{ flex: 1 }}>
              <div className="side-card__title">SDK Python</div>
              <div className="side-card__meta">Ingestion source</div>
            </div>
          </div>
          <div className="side-card__healthy">Healthy</div>
          <div className="side-card__lastseen">Last seen: 1m ago</div>
        </div>
      </div>
    </aside>
  );
}
