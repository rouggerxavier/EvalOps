/** Consume each opened fragment; the component keeps the result only in its ref. */
export function takeRecoveryFragment(location: Pick<Location, "hash" | "pathname">, history: Pick<History, "replaceState" | "state">): string {
  const token = location.hash.slice(1);
  const valid = /^[A-Za-z0-9_-]{43}$/.test(token);
  // shortcut: Next history here is JSON; use structured-clone traversal if non-JSON state is introduced.
  const state = JSON.parse(JSON.stringify(history.state, (_key, value) => {
    if (typeof value !== "string" || !token) return value;
    const withoutFragment = value.replaceAll(`#${token}`, "");
    return valid ? withoutFragment.replaceAll(token, "") : withoutFragment;
  }));
  history.replaceState(state, "", location.pathname);
  return valid ? token : "";
}
