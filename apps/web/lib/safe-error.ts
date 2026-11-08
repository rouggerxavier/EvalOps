// A-12: single source of truth for turning a raw API/runtime error into
// a safe, user-facing message. Imported by server actions
// (lib/actions.ts) AND by page/error boundaries (Server + Client
// Components) — so this module stays free of server-action directives and of any
// server-only imports.
//
// `requestJson` in lib/api.ts throws `new Error("API <status>: <raw
// backend body>")`. Rendering that raw can leak SQL / tracebacks /
// paths / tokens straight to the UI. Everything user-visible must pass
// through `sanitizeApiError` / `safeErrorMessage` first.
//
// IMPORTANT: the logic below is mirrored in plain JS in
// tests/security.test.mjs (the `node --test` runner has no TS loader).
// When you change a rule here, mirror it there so that safety net
// stays accurate.

const SAFE_HTTP_MESSAGES: Record<number, string> = {
  400: "Dados inválidos. Verifique os campos e tente novamente.",
  401: "Sessão expirada ou não autorizado. Faça login novamente.",
  402: "Limite do plano atingido.",
  403: "Sem permissão para esta ação.",
  404: "Recurso não encontrado.",
  409: "Conflito: o recurso já existe ou foi modificado.",
  410: "Export expirado. Gere um novo arquivo.",
  413: "Payload muito grande.",
  422: "Dados inválidos. Verifique os campos e tente novamente.",
  429: "Muitas requisições. Aguarde e tente novamente.",
};

// Known FastAPI ``detail`` codes that should override the generic status copy.
// Keep this list tight — only codes vetted as safe (no PII, no schema leak).
const SAFE_DETAIL_MESSAGES: Record<string, string> = {
  project_slug_taken: "Este slug já está em uso nesta organização. Escolha outro.",
  organization_slug_taken: "Este slug de organização já está em uso. Escolha outro.",
  api_key_not_revoked: "Revogue a chave antes de excluí-la.",
  invalid_rubric: "Rubrica inválida. Confira o YAML e tente novamente.",
  sampling_rubric_required: "Informe a rubrica e sua versão juntas.",
  rubric_version_not_found: "Esta versão da rubrica não existe. Confira o número da versão.",
};

export const GENERIC_ERROR = "Algo deu errado. Tente novamente.";

const LEAK_PATTERNS = [
  /traceback\s+\(most recent call last\)/i,
  /sqlalchemy/i,
  /sqlite/i,
  /psycopg/i,
  /postgres/i,
  /\b(?:IntegrityError|OperationalError|ProgrammingError)\b/,
  /\b(?:no such table|database is locked|constraint failed|unique constraint failed|foreign key constraint failed)\b/i,
  /\b(?:relation|column|table)\s+['"]?[\w.]+['"]?\s+does not exist\b/i,
  /\b(?:select|insert|update|delete)\b.{1,80}\b(?:from|into|set|where|values)\b/is,
  /file ".*\.py"/i,
  /line \d+, in /i,
  /(?:^|[\s'"(=])(?:\/(?:home|users|var|tmp|etc|root|opt|mnt)\/|[A-Za-z]:\\)/i,
  /\.venv[\\/]/i,
  / object at 0x[0-9a-fA-F]+/i,
  /eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}/,
  /\bevk_[a-z0-9_]{4,}/i,
  /\bsk-[A-Za-z0-9_-]{8,}/,
  /\bbearer\s+\S{6,}/i,
  /\bset-cookie\b/i,
  /\b(?:password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)\b\s*[=:]\s*\S/i,
];

const INVALID_RUBRIC_PREFIX = "Rubrica inválida: ";

function hasLeak(text: string): boolean {
  return LEAK_PATTERNS.some((pattern) => pattern.test(text));
}

// The parser's reason names the YAML field to fix. A link is never part of one, and
// this text can also arrive through the URL, so links fall back to the generic copy.
function isSafeRubricMessage(message: string): boolean {
  return (
    message.startsWith(INVALID_RUBRIC_PREFIX) &&
    message.length <= 240 &&
    !/https?:|www\./i.test(message) &&
    !hasLeak(message)
  );
}

function invalidRubricMessage(body: string): string | null {
  try {
    const detail: unknown = JSON.parse(body).detail;
    if (typeof detail !== "string" || !detail.startsWith("invalid_rubric: ")) return null;
    const message = INVALID_RUBRIC_PREFIX + detail.slice("invalid_rubric: ".length);
    return isSafeRubricMessage(message) ? message : null;
  } catch {
    return null;
  }
}

/**
 * Map a thrown error message to a safe, user-facing string.
 *
 * `API <status>: ...` errors (from lib/api.ts) collapse to a friendly
 * per-status message. Anything else that matches a leak pattern — or
 * any unrecognised message — collapses to the generic fallback. The
 * raw text is never returned.
 */
export function sanitizeApiError(message: string): string {
  const match = /^API (\d{3}):\s*(.*)$/.exec(message);
  if (match) {
    const httpStatus = parseInt(match[1], 10);
    const body = match[2];
    // Prefer a vetted, specific copy when the backend returned a known
    // ``detail`` code (e.g. ``project_slug_taken``). Falls through to the
    // generic per-status message if the code isn't on the allowlist.
    const rubricMessage = invalidRubricMessage(body);
    if (rubricMessage) return rubricMessage;
    const detailMatch = /"detail"\s*:\s*"([a-z0-9_]+)"/i.exec(body);
    if (detailMatch) {
      const safeDetail = SAFE_DETAIL_MESSAGES[detailMatch[1]];
      if (safeDetail) return safeDetail;
    }
    return SAFE_HTTP_MESSAGES[httpStatus] ?? GENERIC_ERROR;
  }
  // Server actions redirect with an already-sanitized message and pages sanitize it again.
  if (Object.values(SAFE_HTTP_MESSAGES).includes(message)) return message;
  if (Object.values(SAFE_DETAIL_MESSAGES).includes(message)) return message;
  if (isSafeRubricMessage(message)) return message;
  return GENERIC_ERROR;
}

/**
 * Sanitize an unknown thrown value for display. `Error`/string inputs
 * go through `sanitizeApiError`; anything else yields `fallback`
 * (a caller-supplied, context-specific safe sentence).
 */
export function safeErrorMessage(error: unknown, fallback: string = GENERIC_ERROR): string {
  if (error instanceof Error) return sanitizeApiError(error.message);
  if (typeof error === "string") return sanitizeApiError(error);
  return fallback;
}

/** Notice for rubric fields the API accepted but nothing reads. `raw` comes from the URL. */
export function ignoredFieldsNotice(raw: string | undefined): string | null {
  if (!raw || !/^[a-z_,]+$/.test(raw)) return null;
  return `Campos sem efeito, que nada lê: ${raw.split(",").join(", ")}.`;
}
