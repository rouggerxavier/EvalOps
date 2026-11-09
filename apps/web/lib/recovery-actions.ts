"use server";

import { redirect } from "next/navigation";
import { AuthError, clearSessionCookie, recoverPasswordWithApi } from "./auth";

export type RecoveryState = { error?: string; sent?: boolean };

export async function forgotPasswordAction(_previous: RecoveryState, form: FormData): Promise<RecoveryState> {
  const email = String(form.get("email") ?? "").trim().toLowerCase();
  if (email.length > 320 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return { error: "invalid_email" };
  try {
    await recoverPasswordWithApi("forgot-password", { email });
    return { sent: true };
  } catch (error) {
    return { error: error instanceof AuthError && error.status === 429 ? "too_many_attempts" : "unavailable" };
  }
}

export async function resetPasswordAction(form: FormData): Promise<RecoveryState> {
  const token = String(form.get("token") ?? "");
  const password = String(form.get("new_password") ?? "");
  const confirmation = String(form.get("confirm_password") ?? "");
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return { error: "invalid_reset" };
  if (Array.from(password).length < 8 || Array.from(password).length > 256) return { error: "invalid_password" };
  if (password !== confirmation) return { error: "password_mismatch" };
  try {
    await recoverPasswordWithApi("reset-password", { token, new_password: password });
  } catch (error) {
    return { error: error instanceof AuthError && error.status === 400 ? "invalid_reset"
      : error instanceof AuthError && error.status === 422 ? "invalid_password"
      : error instanceof AuthError && error.status === 429 ? "too_many_attempts" : "unavailable" };
  }
  await clearSessionCookie();
  redirect("/login?password_changed=1");
}
