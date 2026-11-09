/** Read once per mounted form; the component keeps the result only in its ref. */
export function takeRecoveryFragment(location: Pick<Location, "hash" | "pathname">, history: Pick<History, "replaceState" | "state">): string {
  const token = location.hash.slice(1);
  history.replaceState(history.state, "", location.pathname);
  return /^[A-Za-z0-9_-]{43}$/.test(token) ? token : "";
}
