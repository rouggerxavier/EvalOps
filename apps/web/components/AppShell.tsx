import type { ReactNode } from "react";
import { Suspense } from "react";
import { cookies } from "next/headers";

import { EvoShortcuts } from "@/components/EvoShortcuts";
import { EvoToastBridge } from "@/components/EvoToastBridge";
import { EvoToastHost } from "@/components/EvoToastHost";
import { EvoTopbar } from "@/components/EvoTopbar";
import { Sidebar } from "@/components/Sidebar";
import { getNotifications, getProjects, resolveProject } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

const ENV_COOKIE = "evalops_env";
const VALID_ENVS = new Set(["dev", "staging", "prod"]);

type Props = {
  children: ReactNode;
  org: string;
  project: string;
  initials: string;
};

export async function AppShell({ children, org, project, initials }: Props) {
  const resolved = await resolveProject(org, project).catch(() => null);
  const cookieStore = await cookies();
  const envCookie = cookieStore.get(ENV_COOKIE)?.value;
  // No cookie means no filter: the chip must not claim an environment the data ignores.
  const environment: "all" | "dev" | "staging" | "prod" = VALID_ENVS.has(envCookie ?? "")
    ? (envCookie as "dev" | "staging" | "prod")
    : "all";

  let notifications: NotificationItem[] = [];
  let projects: { org: string; project: string; label: string }[] = [{ org, project, label: project }];

  if (resolved) {
    const [notifResult, projectsResult] = await Promise.allSettled([
      getNotifications(resolved.project_id),
      getProjects(resolved.org_id),
    ]);
    if (notifResult.status === "fulfilled") notifications = notifResult.value.data;
    if (projectsResult.status === "fulfilled") {
      projects = projectsResult.value.data.map((p) => ({ org, project: p.slug, label: p.name }));
    }
  }

  return (
    <div className="app-shell evo-shell">
      <Sidebar org={org} project={project} />
      <div className="app-main evo-main">
        <EvoTopbar
          org={org}
          project={project}
          initials={initials}
          notifications={notifications}
          projects={projects}
          projectId={resolved?.project_id ?? null}
          environment={environment}
        />
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
