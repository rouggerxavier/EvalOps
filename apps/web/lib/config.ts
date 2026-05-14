/**
 * Centralized environment-driven configuration for the web app.
 *
 * Phase 1 hardening rules:
 *  - G-04: in production, EVALOPS_API_BASE_URL must be set and must not
 *    point at localhost/127.0.0.1. Otherwise getApiBaseUrl() throws.
 *  - G-03: the dashboard bearer fallback (EVALOPS_DASHBOARD_BEARER_TOKEN)
 *    is only honoured when NODE_ENV !== "production" AND
 *    EVALOPS_DEV_MODE === "1".
 *
 * Validation happens lazily (per-call) so that `next build` does not fail
 * just because env vars are absent at static-analysis time. The runtime
 * request path will still throw if a misconfigured production server tries
 * to issue an API call — that is the intended fail-loud behaviour.
 */

const PRODUCTION = process.env.NODE_ENV === "production";
const LOCAL_DEFAULT_BASE = "http://localhost:8000/v1";

function isLocalhostUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return u.hostname === "localhost" || u.hostname === "127.0.0.1";
  } catch {
    return false;
  }
}

export class ApiBaseUrlError extends Error {
  code: "missing" | "localhost";
  constructor(code: "missing" | "localhost", message: string) {
    super(message);
    this.code = code;
    this.name = "ApiBaseUrlError";
  }
}

export function getApiBaseUrl(): string {
  const raw = process.env.EVALOPS_API_BASE_URL;
  if (PRODUCTION) {
    if (!raw || raw.trim() === "") {
      throw new ApiBaseUrlError(
        "missing",
        "EVALOPS_API_BASE_URL must be set in production",
      );
    }
    if (isLocalhostUrl(raw)) {
      throw new ApiBaseUrlError(
        "localhost",
        "EVALOPS_API_BASE_URL cannot point to localhost in production",
      );
    }
    return raw;
  }
  return raw && raw.trim() ? raw : LOCAL_DEFAULT_BASE;
}

export function isDevMode(): boolean {
  return !PRODUCTION && process.env.EVALOPS_DEV_MODE === "1";
}

export function isProduction(): boolean {
  return PRODUCTION;
}
