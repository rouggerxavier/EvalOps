import type { ReactNode } from "react";
import { Bell, Calendar, ChevronDown, Search, Star } from "lucide-react";
import { redirect } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { UserMenu } from "@/components/UserMenu";
import { getSession, hasFallbackToken } from "@/lib/auth";

type Props = {
  children: ReactNode;
  params: Promise<{ org: string; project: string }>;
};

export default async function ProjectLayout({ children, params }: Props) {
  const { org, project } = await params;
  const session = await getSession();
  if (!session && !hasFallbackToken()) {
    redirect("/login");
  }
  const initials = session?.user?.name
    ? session.user.name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() ?? "")
        .join("") || org.substring(0, 2).toUpperCase()
    : org.substring(0, 2).toUpperCase();

  return (
    <div className="app">
      <Sidebar org={org} project={project} />

      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <header className="topbar">
          <div className="project-picker">
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="project-picker__label">Project</span>
              <span className="project-picker__name">{project}</span>
            </div>
            <ChevronDown size={14} />
          </div>

          <button className="icon-btn" aria-label="Star project" style={{ background: "rgba(245,185,69,0.10)", color: "var(--warning)", borderColor: "rgba(245,185,69,0.25)" }}>
            <Star size={14} />
          </button>

          <div className="env-pill">
            Prod <ChevronDown size={12} />
          </div>

          <div className="topbar__spacer" />

          <button className="tb-control">
            <Calendar size={14} />
            <span>Last 7 days</span>
            <ChevronDown size={14} />
          </button>

          <div className="search">
            <Search size={14} />
            <input placeholder="Search traces, evals, rubrics…" />
            <span className="kbd">/</span>
          </div>

          <button className="icon-btn" aria-label="Notifications">
            <Bell size={16} />
            <span className="dot" />
          </button>

          <UserMenu initials={initials} email={session?.user?.email} name={session?.user?.name} />
        </header>

        {children}
      </div>
    </div>
  );
}
