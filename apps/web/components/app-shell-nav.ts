export type AppShellNavItem = {
  id: string;
  label: string;
  path: string;
  shortcut?: string;
};

export type AppShellNavSection = {
  label: string;
  items: AppShellNavItem[];
};

export const APP_SHELL_NAV_SECTIONS: AppShellNavSection[] = [
  {
    label: "Projeto",
    items: [
      { id: "overview", label: "Visão geral", path: "", shortcut: "G O" },
      { id: "traces", label: "Traces", path: "/traces", shortcut: "G T" },
      { id: "evaluations", label: "Avaliações", path: "/evaluations", shortcut: "G E" },
    ],
  },
  {
    label: "Recursos",
    items: [
      { id: "prompts", label: "Prompts", path: "/prompts", shortcut: "G P" },
      { id: "rubrics", label: "Rubricas", path: "/rubrics", shortcut: "G R" },
      { id: "datasets", label: "Datasets", path: "/datasets", shortcut: "G D" },
      { id: "experiments", label: "Experimentos", path: "/experiments", shortcut: "G X" },
    ],
  },
  {
    label: "Operação",
    items: [
      { id: "keys", label: "Chaves de API", path: "/keys", shortcut: "G K" },
      { id: "exports", label: "Exports", path: "/exports" },
      { id: "settings", label: "Ajustes", path: "/settings", shortcut: "G S" },
    ],
  },
];

export const APP_SHELL_NAV_ITEMS = APP_SHELL_NAV_SECTIONS.flatMap((section) => section.items);

export function projectHref(base: string, path: string, environment?: string | null): string {
  const href = path === "" ? base : `${base}${path}`;
  return environment == null ? href : `${href}?environment=${encodeURIComponent(environment)}`;
}

export function getActiveNavItem(pathname: string, base: string): AppShellNavItem {
  const subPath = pathname.startsWith(base) ? pathname.slice(base.length).replace(/\/$/, "") : "";
  const item = APP_SHELL_NAV_ITEMS
    .filter((entry) => entry.path === subPath || (entry.path !== "" && subPath.startsWith(`${entry.path}/`)))
    .sort((a, b) => b.path.length - a.path.length)[0];

  return item ?? APP_SHELL_NAV_ITEMS[0];
}

export function getPageTitle(pathname: string, base: string): string {
  const activeItem = getActiveNavItem(pathname, base);
  const subPath = pathname.startsWith(base) ? pathname.slice(base.length).replace(/\/$/, "") : "";

  if (subPath === "/traces/compare") {
    return "Comparar traces";
  }

  if (subPath.startsWith("/traces/")) {
    return "Detalhe do trace";
  }

  return activeItem.label;
}
