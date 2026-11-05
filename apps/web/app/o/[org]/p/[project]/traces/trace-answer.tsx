import type { ReactNode } from "react";

import { messageText } from "@/lib/trace-display";
import type { TraceSpan } from "@/lib/types";

export function getAssistantAnswer(spans: TraceSpan[]): string | null {
  for (const span of [...spans].reverse()) {
    for (const message of [...(span.messages_out ?? [])].reverse()) {
      if (message.role === "assistant") {
        const text = messageText(message);
        if (text) return text;
      }
    }
  }
  return null;
}

export function highlightUnsupported(text: string, claims: string[]): ReactNode {
  const matched = claims
    .filter((claim) => claim.length > 0)
    .map((claim) => ({ claim, index: text.indexOf(claim) }))
    .filter((match) => match.index >= 0)
    .sort((a, b) => a.index - b.index);

  if (matched.length === 0) return text;

  const parts: ReactNode[] = [];
  let cursor = 0;
  for (const match of matched) {
    if (match.index < cursor) continue;
    parts.push(text.slice(cursor, match.index));
    parts.push(
      <mark className="ops-detail__answer--unsupported ops-compare__answer--unsupported" key={`${match.index}:${match.claim}`}>
        {match.claim}
      </mark>,
    );
    cursor = match.index + match.claim.length;
  }
  parts.push(text.slice(cursor));
  return parts;
}

export function TraceAnswer({
  spans,
  unsupportedClaims = [],
  redacted = false,
}: {
  spans: TraceSpan[];
  unsupportedClaims?: string[];
  redacted?: boolean;
}) {
  const answer = getAssistantAnswer(spans);
  return answer ? (
    <p className="ops-compare__answer-text">{highlightUnsupported(answer, unsupportedClaims)}</p>
  ) : (
    <p className="t__empty">
      {redacted ? "Trace redigido: o texto da resposta não foi guardado." : "Sem dados de resposta neste trace."}
    </p>
  );
}
