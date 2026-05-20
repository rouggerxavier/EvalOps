import type { ReactNode } from "react";

import { EvoTopbar } from "@/components/EvoTopbar";
import { KeyboardShortcuts } from "@/components/KeyboardShortcuts";
import { Sidebar } from "@/components/Sidebar";

type Props = {
  children: ReactNode;
  org: string;
  project: string;
  initials: string;
};

export function AppShell({ children, org, project, initials }: Props) {
  return (
    <div className="evo-shell">
      <KeyboardShortcuts org={org} project={project} />
      <Sidebar org={org} project={project} />
      <div className="evo-main">
        <EvoTopbar org={org} project={project} initials={initials} />
        {children}
      </div>
    </div>
  );
}
