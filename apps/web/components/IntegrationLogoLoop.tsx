"use client";

import styles from "./IntegrationLogoLoop.module.css";

const INTEGRATIONS = ["OpenAI", "Anthropic", "Gemini", "Groq", "LiteLLM", "LangGraph", "OpenTelemetry"];

export function IntegrationLogoLoop() {
  return (
    <div className={styles.wrap}>
      <p className={styles.copy}>Integre com os modelos, runtimes e padrões que seu time já usa.</p>
      <div className={styles.surface} role="region" aria-label="Ecossistema suportado">
        <ul className={styles.logoRow}>
          {INTEGRATIONS.map((name) => (
            <li key={name} className={styles.logoItem}>
              <span className={styles.logoText}>{name}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
