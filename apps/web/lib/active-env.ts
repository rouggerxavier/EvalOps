import { cookies } from "next/headers";
import { resolveEnvironment, type Environment } from "./environment";

const ENV_COOKIE = "evalops_env";

/**
 * Single source of truth for the "active" environment on a server-rendered page.
 *
 * Resolution order:
 * 1. `?environment=` query string — wins, because it's an explicit caller intent
 *    (deep-link, env switcher just submitted, etc.).
 * 2. `evalops_env` cookie — the last value the user picked, persisted across
 *    pages/navigation.
 * 3. `undefined` — caller treats it as "all environments".
 *
 * An empty `?environment=` is the filter's "qualquer env": an explicit "all" that
 * must beat the cookie for this view.
 *
 * Centralising this avoids the bug where the topbar selector wrote a cookie but
 * pages still read only the query string, so switching the chip didn't filter
 * any data.
 */
export async function getActiveEnvironment(qpEnv: string | undefined): Promise<Environment | undefined> {
  if (qpEnv === "") return undefined;
  const queryEnvironment = resolveEnvironment(qpEnv);
  if (queryEnvironment) return queryEnvironment;
  const store = await cookies();
  const cookieValue = store.get(ENV_COOKIE)?.value;
  return resolveEnvironment(qpEnv, cookieValue);
}
