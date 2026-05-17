import { NextResponse, type NextRequest } from "next/server";

import { getAuthToken } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/config";
import { sanitizeApiError } from "@/lib/safe-error";

export const dynamic = "force-dynamic";

const DOWNLOAD_STATUS_MESSAGES: Record<number, string> = {
  404: "Arquivo de export não encontrado.",
  409: "Export ainda em processamento. Tente novamente em instantes.",
  410: "Export expirado. Gere um novo arquivo.",
};

function safeFilenameToken(value: string): string {
  const sanitized = value.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
  return sanitized || "export";
}

function safeRedirectPath(raw: string | null): string {
  if (!raw) return "/";
  if (raw.startsWith("/o/")) return raw;
  return "/";
}

function redirectWithError(request: NextRequest, path: string, message: string): NextResponse {
  const redirectUrl = new URL(path, request.url);
  redirectUrl.searchParams.set("error", message);
  return NextResponse.redirect(redirectUrl);
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ exportId: string }> },
): Promise<Response> {
  const { exportId } = await params;
  const redirectPath = safeRedirectPath(request.nextUrl.searchParams.get("redirect"));

  const token = await getAuthToken();
  if (!token) {
    return redirectWithError(
      request,
      redirectPath,
      sanitizeApiError("API 401: auth_required"),
    );
  }

  let upstream: Response;
  try {
    const apiBaseUrl = getApiBaseUrl();
    upstream = await fetch(`${apiBaseUrl}/exports/${encodeURIComponent(exportId)}/download`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    return redirectWithError(
      request,
      redirectPath,
      sanitizeApiError("API 500: export_download_failed"),
    );
  }

  if (!upstream.ok) {
    const statusMessage =
      DOWNLOAD_STATUS_MESSAGES[upstream.status] ??
      sanitizeApiError(`API ${upstream.status}: export_download_failed`);
    return redirectWithError(request, redirectPath, statusMessage);
  }

  const headers = new Headers();
  headers.set("Content-Type", upstream.headers.get("content-type") ?? "application/x-ndjson");
  headers.set(
    "Content-Disposition",
    upstream.headers.get("content-disposition") ??
      `attachment; filename="export-${safeFilenameToken(exportId)}.jsonl"`,
  );
  headers.set("Cache-Control", "no-store");

  return new Response(upstream.body, {
    status: 200,
    headers,
  });
}
