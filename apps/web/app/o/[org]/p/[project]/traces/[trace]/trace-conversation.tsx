import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { formatCost, formatLatency } from "@/lib/format";
import { messageText } from "@/lib/trace-display";
import type { TraceSpan } from "@/lib/types";
import { highlightUnsupported } from "../trace-answer";

type Message = Record<string, unknown>;

const SECTION_STYLE = {
  padding: "14px 16px",
  borderBottom: "1px solid var(--border-subtle)",
  display: "flex",
  flexDirection: "column",
  gap: 10,
} as const;

const SUMMARY_STYLE = { cursor: "pointer", fontSize: 12, color: "var(--fg-3)" } as const;

function MessageBlock({ message, unsupportedClaims = [] }: { message: Message; unsupportedClaims?: string[] }) {
  const text = messageText(message);
  const toolCalls = message.tool_calls;
  const role = typeof message.role === "string" ? message.role : "mensagem";
  const label = role === "user" ? "Cliente perguntou" : role === "assistant" ? "A IA respondeu" : role;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span className="ops-detail__conversation-label">
        {label}
      </span>
      {text ? (
        <p className="ops-detail__conversation-text">
          {role === "assistant" ? highlightUnsupported(text, unsupportedClaims) : text}
        </p>
      ) : null}
      {Array.isArray(toolCalls) && toolCalls.length > 0 ? (
        <details>
          <summary style={SUMMARY_STYLE}>
            {toolCalls.length} chamada{toolCalls.length === 1 ? "" : "s"} de ferramenta
          </summary>
          <JsonBlock value={toolCalls} />
        </details>
      ) : null}
    </div>
  );
}

function SpanFacts({ span }: { span: TraceSpan }) {
  const facts = [
    span.model ? (span.provider ? `${span.provider}/${span.model}` : span.model) : null,
    span.tokens_in !== null || span.tokens_out !== null ? `${span.tokens_in ?? 0} → ${span.tokens_out ?? 0} tokens` : null,
    formatLatency(span.duration_ms),
    span.cost_usd !== null ? formatCost(span.cost_usd) : null,
    span.prompt_version_ref ?? null,
  ].filter(Boolean);
  return (
    <div className="row" style={{ gap: 8, flexWrap: "wrap", justifyContent: "space-between" }}>
      <strong style={{ fontSize: 13, color: "var(--fg-2)", fontWeight: 600, overflowWrap: "anywhere" }}>{span.name}</strong>
      <span className="mono" style={{ fontSize: 11, color: "var(--fg-3)", overflowWrap: "anywhere" }}>
        {facts.join(" · ")}
      </span>
    </div>
  );
}

function LlmSpan({ span, unsupportedClaims }: { span: TraceSpan; unsupportedClaims: string[] }) {
  const input = (span.messages_in ?? []) as Message[];
  const output = (span.messages_out ?? []) as Message[];
  const earlier = input.slice(0, -1);
  const last = input.at(-1);
  return (
    <div style={SECTION_STYLE}>
      <SpanFacts span={span} />
      {earlier.length > 0 ? (
        <details>
          <summary style={SUMMARY_STYLE}>
            {earlier.length} mensage{earlier.length === 1 ? "m anterior" : "ns anteriores"} no contexto
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
            {earlier.map((message, index) => (
              <MessageBlock key={index} message={message} unsupportedClaims={unsupportedClaims} />
            ))}
          </div>
        </details>
      ) : null}
      {last ? <MessageBlock message={last} unsupportedClaims={unsupportedClaims} /> : null}
      {output.map((message, index) => (
        <MessageBlock key={index} message={message} unsupportedClaims={unsupportedClaims} />
      ))}
      {output.length === 0 && span.output ? <JsonBlock value={span.output} /> : null}
      {span.error ? <SpanError span={span} /> : null}
    </div>
  );
}

function SpanError({ span }: { span: TraceSpan }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Badge variant="err">erro</Badge>
      <JsonBlock value={span.error} />
    </div>
  );
}

function OtherSpan({ span }: { span: TraceSpan }) {
  return (
    <div style={SECTION_STYLE}>
      <SpanFacts span={span} />
      <details>
        <summary style={SUMMARY_STYLE}>Entrada e saída de {span.type}</summary>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
          {span.input ? <JsonBlock value={span.input} /> : null}
          {span.output ? <JsonBlock value={span.output} /> : null}
        </div>
      </details>
      {span.error ? <SpanError span={span} /> : null}
    </div>
  );
}

function hasContent(span: TraceSpan): boolean {
  return Boolean(span.messages_in?.length || span.messages_out?.length || span.input || span.output || span.error);
}

export function TraceConversation({
  spans,
  redacted,
  unsupportedClaims = [],
  evaluationReason,
}: {
  spans: TraceSpan[];
  redacted: boolean;
  unsupportedClaims?: string[];
  evaluationReason?: string | null;
}) {
  const visible = spans.filter(hasContent);
  return (
    <Card title="Conversa" subtitle="O que entrou e saiu de cada etapa, em ordem" flush className="ops-detail__responses">
      {visible.length === 0 ? (
        <div className="t__empty">
          {redacted
            ? "Trace redigido: os textos não foram guardados."
            : "Este trace não tem mensagens. No SDK, registre a chamada com span.set_llm(messages_in=..., messages_out=...)."}
        </div>
      ) : (
          visible.map((span) =>
          span.type === "llm_call" ? <LlmSpan key={span.id} span={span} unsupportedClaims={unsupportedClaims} /> : <OtherSpan key={span.id} span={span} />,
        )
      )}
      {evaluationReason ? (
        <div className="ops-detail__why">
          <strong>Por que foi reprovada:</strong> {evaluationReason}
        </div>
      ) : null}
    </Card>
  );
}
