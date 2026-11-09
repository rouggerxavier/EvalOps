"use server";

import { redirect } from "next/navigation";

import {
  AuthError,
  clearSessionCookie,
  changePasswordWithApi,
  getSessionCookieToken,
  loginWithApi,
  logoutWithApi,
  registerWithApi,
} from "./auth";

const PASSWORD_MIN = 8;

function detailToFriendly(detail: string): string {
  switch (detail) {
    case "invalid_credentials":
      return "Invalid email or password.";
    case "email_taken":
      return "An account with that email already exists.";
    default:
      if (detail && detail.length < 200) return detail;
      return "Something went wrong. Please try again.";
  }
}

function redirectWithError(path: string, error: string, fields: Record<string, string> = {}): never {
  const sp = new URLSearchParams({ error });
  for (const [k, v] of Object.entries(fields)) {
    if (v) sp.set(k, v);
  }
  redirect(`${path}?${sp.toString()}`);
}

export async function loginAction(formData: FormData): Promise<void> {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");

  if (!email || !password) {
    redirectWithError("/login", "Email and password are required.", { email });
  }

  try {
    await loginWithApi({ email, password });
  } catch (error) {
    const msg = error instanceof AuthError ? detailToFriendly(error.message) : "Could not reach the API. Try again in a moment.";
    redirectWithError("/login", msg, { email });
  }

  redirect("/app");
}

export async function registerAction(formData: FormData): Promise<void> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const orgName = String(formData.get("org_name") ?? "").trim() || undefined;
  const projectName = String(formData.get("project_name") ?? "").trim() || undefined;

  if (!name || !email || !password) {
    redirectWithError("/register", "Name, email and password are required.", { name, email });
  }
  if (password.length < PASSWORD_MIN) {
    redirectWithError("/register", `Password must be at least ${PASSWORD_MIN} characters.`, { name, email });
  }

  try {
    await registerWithApi({
      email,
      name,
      password,
      org_name: orgName,
      project_name: projectName,
    });
  } catch (error) {
    const msg = error instanceof AuthError ? detailToFriendly(error.message) : "Could not reach the API. Try again in a moment.";
    redirectWithError("/register", msg, { name, email });
  }

  redirect("/app");
}

export async function logoutAction(): Promise<void> {
  try {
    const sessionToken = await getSessionCookieToken();
    if (sessionToken) {
      await logoutWithApi(sessionToken);
    }
  } catch {
    // Best effort revoke on backend; local logout must still succeed.
  }

  await clearSessionCookie();
  redirect("/");
}

export async function changePasswordAction(formData: FormData): Promise<void> {
  const token = await getSessionCookieToken();
  if (!token) redirect("/login");

  const currentPassword = String(formData.get("current_password") ?? "");
  const newPassword = String(formData.get("new_password") ?? "");
  const confirmation = String(formData.get("confirm_password") ?? "");
  if (!currentPassword || Array.from(currentPassword).length > 256 ||
      Array.from(newPassword).length < PASSWORD_MIN || Array.from(newPassword).length > 256) {
    redirect("/account?error=invalid_password");
  }
  if (newPassword !== confirmation) redirect("/account?error=password_mismatch");

  let failure: string | null = null;
  try {
    await changePasswordWithApi(token, { current_password: currentPassword, new_password: newPassword });
  } catch (error) {
    if (error instanceof AuthError && error.status === 401) {
      await clearSessionCookie();
      redirect("/login?session_expired=1");
    }
    failure = error instanceof AuthError && error.status === 400 ? "invalid_current_password"
      : error instanceof AuthError && error.status === 422 ? "invalid_password"
      : error instanceof AuthError && error.status === 429 ? "too_many_attempts"
      : "unavailable";
  }
  if (failure) redirect(`/account?error=${failure}`);

  await clearSessionCookie();
  redirect("/login?password_changed=1");
}
