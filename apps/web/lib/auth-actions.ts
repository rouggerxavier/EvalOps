"use server";

import { redirect } from "next/navigation";

import {
  AuthError,
  clearSessionCookie,
  loginWithApi,
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
  await clearSessionCookie();
  redirect("/");
}
