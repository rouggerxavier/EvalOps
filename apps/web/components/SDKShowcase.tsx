"use client";

import Link from "next/link";
import { BookOpen, Check, Copy, Github } from "lucide-react";
import { useMemo, useState } from "react";

import { SDKBorderGlow } from "./SDKBorderGlow";
import styles from "./SDKShowcase.module.css";

const CODE_SNIPPET = `import evalops
from openai import OpenAI

evalops.init(api_key="evk_prod_...", project="docops-agent")
client = OpenAI()

@evalops.trace(name="rag.summarize")
def summarize(question: str, doc: str):
    with evalops.span("retrieve"):
        chunks = retriever(doc, k=8)

    return client.chat.completions.create(
        model="gpt-4o",
        messages=build_prompt(question, chunks),
    )`;

function tokenLine(line: string, index: number) {
  const key = `line-${index}`;

  if (line.startsWith("import ")) {
    return (
      <span key={key}>
        <span className={styles.sdkTokenKeyword}>import</span> <span className={styles.sdkTokenName}>{line.replace("import ", "")}</span>
      </span>
    );
  }

  if (line.startsWith("from ")) {
    const [, mod, , cls] = line.split(" ");
    return (
      <span key={key}>
        <span className={styles.sdkTokenKeyword}>from</span> <span className={styles.sdkTokenName}>{mod}</span>{" "}
        <span className={styles.sdkTokenKeyword}>import</span> <span className={styles.sdkTokenType}>{cls}</span>
      </span>
    );
  }

  if (line.includes("evalops.init(")) {
    return (
      <span key={key} className={styles.sdkEmphasisLine}>
        <span className={styles.sdkTokenName}>evalops</span>.<span className={styles.sdkTokenFn}>init</span>(
        <span className={styles.sdkTokenParam}>api_key</span>=<span className={styles.sdkTokenStr}>"evk_prod_..."</span>,{" "}
        <span className={styles.sdkTokenParam}>project</span>=<span className={styles.sdkTokenStr}>"docops-agent"</span>)
      </span>
    );
  }

  if (line.startsWith("@evalops.trace")) {
    return (
      <span key={key} className={styles.sdkEmphasisLine}>
        <span className={styles.sdkTokenDecorator}>@evalops.trace</span>(
        <span className={styles.sdkTokenParam}>name</span>=<span className={styles.sdkTokenStr}>"rag.summarize"</span>)
      </span>
    );
  }

  if (line.startsWith("def ")) {
    return (
      <span key={key}>
        <span className={styles.sdkTokenKeyword}>def</span> <span className={styles.sdkTokenFn}>summarize</span>(question: str, doc: str):
      </span>
    );
  }

  if (line.includes('with evalops.span("retrieve")')) {
    return (
      <span key={key}>
        {"    "}
        <span className={styles.sdkTokenKeyword}>with</span> <span className={styles.sdkTokenName}>evalops</span>.
        <span className={styles.sdkTokenFn}>span</span>(<span className={styles.sdkTokenStr}>"retrieve"</span>):
      </span>
    );
  }

  if (line.includes("return client.chat.completions.create(")) {
    return (
      <span key={key}>
        {"    "}
        <span className={styles.sdkTokenKeyword}>return</span> <span className={styles.sdkTokenName}>client</span>.chat.completions.
        <span className={styles.sdkTokenFn}>create</span>(
      </span>
    );
  }

  if (line.includes('model="gpt-4o"')) {
    return (
      <span key={key}>
        {"        "}
        <span className={styles.sdkTokenParam}>model</span>=<span className={styles.sdkTokenStr}>"gpt-4o"</span>,
      </span>
    );
  }

  if (line.includes("messages=build_prompt(question, chunks),")) {
    return (
      <span key={key}>
        {"        "}
        <span className={styles.sdkTokenParam}>messages</span>=<span className={styles.sdkTokenFn}>build_prompt</span>(question, chunks),
      </span>
    );
  }

  return <span key={key}>{line}</span>;
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
          Um decorator, um context manager e um uploader em background. O SDK faz batch e retry sem bloquear a
          requisição do usuário.
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
          <span><Check /> OpenTelemetry-compatible</span>
          <span><Check /> Batch + retry built-in</span>
          <span><Check /> No request blocking</span>
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
              <span className={styles.sdkTab}>TypeScript</span>
            </div>
            <button className={styles.sdkCopyButton} type="button" onClick={handleCopy} aria-live="polite">
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy"}
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
