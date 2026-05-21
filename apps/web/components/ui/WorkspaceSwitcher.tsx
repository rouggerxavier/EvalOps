"use client";

import { useRouter } from "next/navigation";

type WorkspaceProject = {
  org: string;
  project: string;
  label: string;
};

type WorkspaceSwitcherProps = {
  current: string;
  projects: WorkspaceProject[];
};

export function WorkspaceSwitcher({ current, projects }: WorkspaceSwitcherProps) {
  const router = useRouter();

  return (
    <select
      className="filter-select"
      value={current}
      onChange={(event) => {
        const project = projects.find((item) => `${item.org}/${item.project}` === event.target.value);
        if (project) router.push(`/o/${project.org}/p/${project.project}`);
      }}
    >
      {projects.map((project) => (
        <option key={`${project.org}/${project.project}`} value={`${project.org}/${project.project}`}>
          {project.label}
        </option>
      ))}
    </select>
  );
}
