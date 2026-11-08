import type { ReactNode } from "react";
import { cookies } from "next/headers";

import { OpsShellFrame } from "@/components/OpsShellFrame";
import {
  getAttention,
  getNotifications,
  getOrganizationSubscription,
  getOrganizationUsage,
  getProjects,
  resolveProject,
} from "@/lib/api";

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

  let notifications: Awaited<ReturnType<typeof getNotifications>>["data"] = [];
  let projects: { org: string; project: string; label: string }[] = [{ org, project, label: project }];
  let attentionCount: number | null = null;
  let usage: { used: number; limit: number } | null = null;

  if (resolved) {
    const [notifResult, projectsResult, attentionResult, usageResult, subscriptionResult] = await Promise.allSettled([
      getNotifications(resolved.project_id),
      getProjects(resolved.org_id),
      getAttention(resolved.project_id),
      getOrganizationUsage(resolved.org_id),
      getOrganizationSubscription(resolved.org_id),
    ]);
    if (notifResult.status === "fulfilled") notifications = notifResult.value.data;
    if (projectsResult.status === "fulfilled") {
      projects = projectsResult.value.data.map((p) => ({ org, project: p.slug, label: p.name }));
    }
    if (attentionResult.status === "fulfilled") attentionCount = attentionResult.value.count;
    if (usageResult.status === "fulfilled" && subscriptionResult.status === "fulfilled") {
      usage = {
        used: usageResult.value.traces_ingested,
        limit: subscriptionResult.value.plan.monthly_trace_limit,
      };
    }
  }

  return (
    <OpsShellFrame
      org={org}
      project={project}
      orgLabel={resolved?.org_name ?? org}
      projectLabel={resolved?.project_name ?? project}
      initials={initials}
      notifications={notifications}
      projects={projects}
      projectId={resolved?.project_id ?? null}
      environment={environment}
      attentionCount={attentionCount}
      usage={usage}
    >
      {children}
    </OpsShellFrame>
  );
}
