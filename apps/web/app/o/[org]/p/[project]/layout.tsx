import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { EvoTopbar } from "@/components/EvoTopbar";
import { Sidebar } from "@/components/Sidebar";
import { getSession, hasFallbackToken } from "@/lib/auth";

type Props = {
  children: ReactNode;
  params: Promise<{ org: string; project: string }>;
};

export default async function ProjetoLayout({ children, params }: Props) {
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
    <div className="evo-shell">
      <Sidebar org={org} project={project} />
      <div className="evo-main">
        <EvoTopbar org={org} project={project} initials={initials} />
        {children}
      </div>
    </div>
  );
}
