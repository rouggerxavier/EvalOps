import { getURLFromRedirectError } from "next/dist/client/components/redirect";
import { isRedirectError } from "next/dist/client/components/redirect-error";

import { retrySamplingAction, saveSamplingAction } from "@/lib/actions";

export async function POST(request: Request): Promise<Response> {
  const requestURL = new URL(request.url);
  // Next can use an internal hostname in request.url; Host identifies the browser-facing origin.
  const host = request.headers.get("host");
  const current = host ? new URL(`${requestURL.protocol}//${host}`) : requestURL;
  if (request.headers.get("origin") !== current.origin) {
    return new Response("Origem não permitida.", { status: 403 });
  }
  let data: FormData;
  try {
    const reader = request.body?.getReader();
    if (!reader) return new Response("Formulário inválido.", { status: 400 });
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 16 * 1024) {
        await reader.cancel();
        return new Response("Formulário muito grande.", { status: 413 });
      }
      chunks.push(value);
    }
    data = await new Response(new Blob(chunks), { headers: { "Content-Type": request.headers.get("content-type") ?? "" } }).formData();
  } catch {
    return new Response("Formulário inválido.", { status: 400 });
  }
  const intent = data.get("intent");
  if (intent !== "save" && intent !== "retry") {
    return new Response("Ação inválida.", { status: 400 });
  }
  try {
    if (intent === "save") await saveSamplingAction(data);
    else await retrySamplingAction(data);
  } catch (error) {
    if (isRedirectError(error)) {
      const path = getURLFromRedirectError(error);
      if (path) {
        const destination = new URL(path, current);
        if (destination.origin === current.origin && destination.pathname.startsWith("/o/")) {
          return Response.redirect(destination, 303);
        }
      }
    }
    return new Response("Não foi possível concluir a ação.", { status: 500 });
  }
  return new Response("Não foi possível concluir a ação.", { status: 500 });
}
