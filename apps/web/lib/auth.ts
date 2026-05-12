import { cookies } from "next/headers";

const API_BASE_URL = process.env.EVALOPS_API_BASE_URL ?? "http://localhost:8000/v1";
const FALLBACK_TOKEN = process.env.EVALOPS_DASHBOARD_BEARER_TOKEN;

export const SESSION_COOKIE = "evalops_session";
const COOKIE_MAX_AGE_DAYS = 30;

export type SessionWorkspace = {
  org_id: string;
  org_slug: string;
  org_name: string;
  project_id: string;
  project_slug: string;
  project_name: string;
};

export type SessionUser = {
  id: string;
  email: string;
  name: string;
};

export type AuthSession = {
  token: string;
  user: SessionUser;
  workspace: SessionWorkspace | null;
};

type AuthResponseBody = {
  token: string;
  user: SessionUser;
  workspace: SessionWorkspace | null;
};

/**
 * Returns the bearer token to send to the API.
 *
 * Order of preference:
 *   1. Session cookie (set after login/register).
 *   2. EVALOPS_DASHBOARD_BEARER_TOKEN env var (dev fallback).
 */
export async function getAuthToken(): Promise<string | null> {
  const sessionToken = await getSessionCookieToken();
  if (sessionToken) return sessionToken;
  return FALLBACK_TOKEN ?? null;
}

async function getSessionCookieToken(): Promise<string | null> {
  const store = await cookies();
  const cookie = store.get(SESSION_COOKIE);
  if (cookie?.value) return cookie.value;
  return null;
}

export function hasFallbackToken(): boolean {
  return Boolean(FALLBACK_TOKEN);
}

async function setSessionCookie(token: string): Promise<void> {
  const store = await cookies();
  store.set({
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * COOKIE_MAX_AGE_DAYS,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.set({
    name: SESSION_COOKIE,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

async function callAuth(path: string, payload: unknown): Promise<AuthResponseBody> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed?.detail) detail = String(parsed.detail);
    } catch {
      // fall through with raw text
    }
    throw new AuthError(detail || `auth_failed_${res.status}`, res.status);
  }
  return JSON.parse(text) as AuthResponseBody;
}

export class AuthError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "AuthError";
  }
}

export async function registerWithApi(payload: {
  email: string;
  name: string;
  password: string;
  org_name?: string;
  project_name?: string;
}): Promise<AuthResponseBody> {
  const body = await callAuth("/auth/register", payload);
  await setSessionCookie(body.token);
  return body;
}

export async function loginWithApi(payload: {
  email: string;
  password: string;
}): Promise<AuthResponseBody> {
  const body = await callAuth("/auth/login", payload);
  await setSessionCookie(body.token);
  return body;
}

/**
 * Returns the current authenticated session, or null if no valid session
 * is available. Probes /v1/auth/session with whatever token we have.
 */
export async function getSession(): Promise<AuthSession | null> {
  const token = await getSessionCookieToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/auth/session`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as AuthResponseBody;
    return { token, user: body.user, workspace: body.workspace };
  } catch {
    return null;
  }
}
