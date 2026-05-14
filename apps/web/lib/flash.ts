"use server";

import { cookies } from "next/headers";

/**
 * One-shot HttpOnly cookie used to deliver a freshly-created API key to the
 * page that renders the post-creation UI. Avoids placing the raw secret in
 * any URL/Referer/server-log surface (G-02).
 */

const FLASH_COOKIE = "evalops_api_key_flash";
const FLASH_TTL_SECONDS = 60;

export type ApiKeyFlash = { key: string; prefix: string };

function cookieOptions(maxAge: number) {
  return {
    name: FLASH_COOKIE,
    httpOnly: true as const,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

export async function setApiKeyFlash(payload: ApiKeyFlash): Promise<void> {
  const store = await cookies();
  store.set({
    ...cookieOptions(FLASH_TTL_SECONDS),
    value: JSON.stringify(payload),
  });
}

export async function consumeApiKeyFlash(): Promise<ApiKeyFlash | null> {
  const store = await cookies();
  const cookie = store.get(FLASH_COOKIE);
  if (!cookie?.value) return null;
  store.set({ ...cookieOptions(0), value: "" });
  try {
    const parsed = JSON.parse(cookie.value);
    if (typeof parsed?.key === "string" && typeof parsed?.prefix === "string") {
      return { key: parsed.key, prefix: parsed.prefix };
    }
    return null;
  } catch {
    return null;
  }
}
