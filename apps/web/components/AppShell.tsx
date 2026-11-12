import type { ReactNode } from "react";

import { OpsShellFrame } from "@/components/OpsShellFrame";
import { getActiveEnvironment } from "@/lib/active-env";
import {
  getAttention,
  getNotifications,
  getOrganizationSubscription,
  getOrganizationUsage,
  getProjects,
  resolveProject,
} from "@/lib/api";

type Props = {
  children: ReactNode;
  org: string;
  project: string;
  initials: string;
};

export async function AppShell({ children, org, project, initials }: Props) {
  const resolved = await resolveProject(org, project).catch(() => null);
  const environment = (await getActiveEnvironment(undefined)) ?? "all";

  let notifications: Awaited<ReturnType<typeof getNotifications>>["data"] = [];
  let projects: { org: string; project: string; label: string }[] = [{ org, project, label: project }];
  let attentionCount: number | null = null;
  let usage: { used: number; limit: number } | null = null;

  if (resolved) {
    const [notifResult, projectsResult, attentionResult, usageResult, subscriptionResult] = await Promise.allSettled([
      getNotifications(resolved.project_id),
      getProjects(resolved.org_id),
      getAttention(resolved.project_id),
      resolved.membership?.permissions.includes("admin") ? getOrganizationUsage(resolved.org_id) : Promise.resolve(null),
      resolved.membership?.permissions.includes("admin") ? getOrganizationSubscription(resolved.org_id) : Promise.resolve(null),
    ]);
    if (notifResult.status === "fulfilled") notifications = notifResult.value.data;
    if (projectsResult.status === "fulfilled") {
      projects = projectsResult.value.data.map((p) => ({ org, project: p.slug, label: p.name }));
    }
    if (attentionResult.status === "fulfilled") attentionCount = attentionResult.value.count;
    if (usageResult.status === "fulfilled" && subscriptionResult.status === "fulfilled" && usageResult.value && subscriptionResult.value) {
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
      permissions={resolved?.membership?.permissions ?? []}
    >
      {children}
    </OpsShellFrame>
  );
}
