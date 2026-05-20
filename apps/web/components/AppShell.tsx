import type { ReactNode } from "react";
import { Suspense } from "react";

import { EvoShortcuts } from "@/components/EvoShortcuts";
import { EvoToastBridge } from "@/components/EvoToastBridge";
import { EvoToastHost } from "@/components/EvoToastHost";
import { EvoTopbar } from "@/components/EvoTopbar";
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
      <Sidebar org={org} project={project} />
      <div className="evo-main">
        <EvoTopbar org={org} project={project} initials={initials} />
        {children}
      </div>
      <EvoShortcuts />
      <Suspense fallback={null}>
        <EvoToastBridge />
      </Suspense>
      <EvoToastHost />
    </div>
  );
}
