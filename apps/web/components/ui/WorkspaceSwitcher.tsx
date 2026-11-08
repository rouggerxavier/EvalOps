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

const NEW_PROJECT_VALUE = "__new_project__";

export function WorkspaceSwitcher({ current, projects }: WorkspaceSwitcherProps) {
  const router = useRouter();
  const currentProject = projects.find((p) => `${p.org}/${p.project}` === current) ?? projects[0];

  return (
    <select
      className="filter-select"
      aria-label="Projeto"
      value={current}
      onChange={(event) => {
        const value = event.target.value;
        if (value === NEW_PROJECT_VALUE) {
          // Route to settings of the currently-active project — that's where
          // the "Novo projeto" form lives. The fragment is informational only.
          if (currentProject) {
            router.push(`/o/${currentProject.org}/p/${currentProject.project}/settings#new-project`);
          }
          return;
        }
        const project = projects.find((item) => `${item.org}/${item.project}` === value);
        if (project) router.push(`/o/${project.org}/p/${project.project}`);
      }}
    >
      {projects.map((project) => (
        <option key={`${project.org}/${project.project}`} value={`${project.org}/${project.project}`}>
          {project.label}
        </option>
      ))}
      <option disabled>──────</option>
      <option value={NEW_PROJECT_VALUE}>+ Novo projeto…</option>
    </select>
  );
}
