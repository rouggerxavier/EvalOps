"use client";

import Link from "next/link";
import { BookOpen, Check, Copy, Github } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import { SDKBorderGlow } from "./SDKBorderGlow";
import styles from "./SDKShowcase.module.css";

// Mirrors the quickstart in app/docs/page.tsx: without set_llm the reply never reaches rubrics or cost.
const CODE_SNIPPET = `import evalops
from openai import OpenAI

evalops.init(api_key="evk_prod_...", project="docops-agent", environment="prod")
client = OpenAI()

@evalops.trace("rag.answer")
def answer(question: str, conversation_id: str) -> str:
    evalops.set_trace(conversation_id=conversation_id)
    messages = [{"role": "user", "content": question}]
    with evalops.span("llm", type="llm_call") as span:
        reply = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages)
        text = reply.choices[0].message.content
        span.set_llm(
            provider="openai",
            model="gpt-4o-mini",
            messages_in=messages,
            messages_out=[{"role": "assistant", "content": text}],
        )
    return text`;

// Groups map to TOKEN_CLASS by position: string, decorator, keyword, name, type, kwarg, call.
const TOKEN = /("[^"]*")|(@[\w.]+)|\b(import|from|def|with|as|return)\b|\b(evalops|client)\b|\b(OpenAI|str)\b|\b(\w+)(?==)|\b(\w+)(?=\()/g;
const TOKEN_CLASS = [
  styles.sdkTokenStr,
  styles.sdkTokenDecorator,
  styles.sdkTokenKeyword,
  styles.sdkTokenName,
  styles.sdkTokenType,
  styles.sdkTokenParam,
  styles.sdkTokenFn,
];
const EMPHASIS = /evalops\.(init|set_trace)\(|@evalops\.trace|span\.set_llm\(/;

function tokenLine(line: string, index: number) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of line.matchAll(TOKEN)) {
    const at = match.index ?? 0;
    if (at > last) parts.push(line.slice(last, at));
    const group = match.slice(1).findIndex((value) => value !== undefined);
    parts.push(
      <span key={at} className={TOKEN_CLASS[group]}>
        {match[0]}
      </span>,
    );
    last = at + match[0].length;
  }
  parts.push(line.slice(last));
  return (
    <span key={`line-${index}`} className={EMPHASIS.test(line) ? styles.sdkEmphasisLine : undefined}>
      {parts}
    </span>
  );
}

export function SDKShowcase() {
  const [copied, setCopied] = useState(false);
  const codeLines = useMemo(() => CODE_SNIPPET.split("\n"), []);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(CODE_SNIPPET);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={styles.sdkShowcaseRoot}>
      <div className={styles.sdkCopySide}>
        <span className="mk-eyebrow">Python SDK</span>
        <h2>Adicione tracing ao seu agente com poucas linhas.</h2>
        <p className="lede">
          Um decorator abre o trace, um span marca cada etapa e set_llm registra a chamada de modelo que as
          rubricas avaliam. O envio roda em background, com batch e retry, sem bloquear a requisição do usuário.
        </p>

        <div className={styles.sdkActions}>
          <Link className="mk-btn mk-btn--secondary" href="/docs">
            <BookOpen />
            Referência do SDK
          </Link>
          <a className="mk-btn mk-btn--ghost" href="https://github.com/rouggerxavier/EvalOps" target="_blank" rel="noreferrer">
            <Github />
            Ver no GitHub
          </a>
        </div>

        <div className={styles.sdkBenefits} aria-label="Benefícios do SDK">
          <span><Check /> Batch e retry embutidos</span>
          <span><Check /> Não bloqueia a requisição</span>
          <span><Check /> Falhas guardadas em dead-letter</span>
        </div>
      </div>

      <div className={styles.sdkCardArea}>
        <SDKBorderGlow
          className={styles.sdkCodeCard}
          edgeSensitivity={30}
          glowColor="192 86 76"
          backgroundColor="#0B1220"
          borderRadius={26}
          glowRadius={34}
          glowIntensity={0.72}
          coneSpread={22}
          animated
          colors={["#29DFFF", "#5B7CFF", "#48FCA5"]}
          fillOpacity={0.18}
        >
          <div className={styles.sdkCardHeader}>
            <div className={styles.sdkTabs}>
              <span className={`${styles.sdkTab} ${styles.sdkTabActive}`}>Python</span>
            </div>
            <button className={styles.sdkCopyButton} type="button" onClick={handleCopy} aria-live="polite">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copiado" : "Copiar"}
            </button>
          </div>
          <div className={styles.sdkCodeViewport}>
            <code className={styles.sdkCode}>
              {codeLines.map((line, index) => (
                <span className={styles.sdkCodeRow} key={`row-${index}`}>
                  <span className={styles.sdkLineNo}>{String(index + 1).padStart(2, "0")}</span>
                  <span className={styles.sdkLineText}>{tokenLine(line, index)}</span>
                </span>
              ))}
            </code>
          </div>
        </SDKBorderGlow>
      </div>
    </div>
  );
}
