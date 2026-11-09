export type Environment = "dev" | "staging" | "prod";

function isEnvironment(value: string | null | undefined): value is Environment {
  return value === "dev" || value === "staging" || value === "prod";
}

export function resolveEnvironment(query: string | null | undefined, fallback?: string): Environment | undefined {
  if (query === "") return undefined;
  if (isEnvironment(query)) return query;
  return isEnvironment(fallback) ? fallback : undefined;
}
