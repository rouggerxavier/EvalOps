"use client";

import type { ReactNode } from "react";
import { Suspense, useEffect, useState } from "react";

import { EvoShortcuts } from "@/components/EvoShortcuts";
import { EvoToastBridge } from "@/components/EvoToastBridge";
import { EvoToastHost } from "@/components/EvoToastHost";
import { EvoTopbar } from "@/components/EvoTopbar";
import { Sidebar } from "@/components/Sidebar";
import type { NotificationItem } from "@/lib/types";

type WorkspaceProject = { org: string; project: string; label: string };
type UsageSummary = { used: number; limit: number } | null;

type Props = {
  children: ReactNode;
  org: string;
  project: string;
  orgLabel: string;
  projectLabel: string;
  initials: string;
  notifications: NotificationItem[];
  projects: WorkspaceProject[];
  projectId: string | null;
  environment: "all" | "dev" | "staging" | "prod";
  attentionCount: number | null;
  usage: UsageSummary;
};

export function OpsShellFrame({
  children,
  org,
  project,
  orgLabel,
  projectLabel,
  initials,
  notifications,
  projects,
  projectId,
  environment,
  attentionCount,
  usage,
}: Props) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    if (!mobileMenuOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const sidebar = document.getElementById("ops-sidebar");
    const focusable = () => Array.from(
      sidebar?.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), select:not([disabled])') ?? [],
    );
    focusable()[0]?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileMenuOpen(false);
        document.querySelector<HTMLButtonElement>(".ops-mobile-menu-toggle")?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileMenuOpen]);

  function closeMobileMenu() {
    setMobileMenuOpen(false);
  }

  return (
    <div className={`app-shell evo-shell ops-shell${mobileMenuOpen ? " ops-menu-open" : ""}`}>
      <Sidebar
        org={org}
        project={project}
        projects={projects}
        attentionCount={attentionCount}
        usage={usage}
        mobileMenuOpen={mobileMenuOpen}
        onNavigate={closeMobileMenu}
      />
      <div className="app-main evo-main ops-main">
        <EvoTopbar
          org={org}
          project={project}
          orgLabel={orgLabel}
          projectLabel={projectLabel}
          initials={initials}
          notifications={notifications}
          projectId={projectId}
          environment={environment}
          mobileMenuOpen={mobileMenuOpen}
          onMenuToggle={() => setMobileMenuOpen((value) => !value)}
        />
        {children}
      </div>
      {mobileMenuOpen ? (
        <button
          type="button"
          className="ops-menu-backdrop"
          aria-label="Fechar menu"
          onClick={closeMobileMenu}
        />
      ) : null}
      <EvoShortcuts />
      <Suspense fallback={null}>
        <EvoToastBridge />
      </Suspense>
      <EvoToastHost />
    </div>
  );
}
