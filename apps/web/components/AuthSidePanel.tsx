import type { ReactNode } from "react";

type Props = {
  variant: "login" | "register";
};

function LoginPanel(): ReactNode {
  return (
    <div className="panel-mock">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--success)",
            boxShadow: "0 0 0 4px var(--success-soft)",
          }}
        />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-2)" }}>
          trace_9f8d2a7c &middot; gpt-4o
        </span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-3)" }}>há 2 min</span>
      </div>
      <div
        style={{
          fontSize: 13,
          color: "var(--fg-2)",
          background: "var(--surface-3)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          padding: 10,
          lineHeight: 1.5,
        }}
      >
        <span style={{ color: "var(--fg-3)", fontSize: 11 }}>user</span>
        <br />
        Resuma o deck de resultados do Q4 e destaque qualquer mudança de guidance.
      </div>
      <div
        style={{
          marginTop: 8,
          fontSize: 13,
          color: "var(--fg-2)",
          background: "var(--surface-3)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          padding: 10,
          lineHeight: 1.5,
        }}
      >
        <span style={{ color: "var(--fg-3)", fontSize: 11 }}>assistant</span>
        <br />
        Receita +14% YoY. Margem operacional estável. Guidance elevado: faixa de lucro líquido anual agora é $4.8&ndash;5.2B (antes
        $4.5&ndash;5.0B).
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 12 }}>
        <div
          style={{
            background: "var(--success-soft)",
            border: "1px solid var(--success-border)",
            borderRadius: 6,
            padding: 8,
          }}
        >
          <div style={{ fontSize: 10, color: "var(--success)" }}>Aderência</div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 700,
              color: "var(--success)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            0.94
          </div>
        </div>
        <div
          style={{
            background: "var(--success-soft)",
            border: "1px solid var(--success-border)",
            borderRadius: 6,
            padding: 8,
          }}
        >
          <div style={{ fontSize: 10, color: "var(--success)" }}>Utilidade</div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 700,
              color: "var(--success)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            0.88
          </div>
        </div>
        <div
          style={{
            background: "var(--warning-soft)",
            border: "1px solid var(--warning-border)",
            borderRadius: 6,
            padding: 8,
          }}
        >
          <div style={{ fontSize: 10, color: "var(--warning)" }}>PII</div>
          <div
            style={{
              fontSize: 16,
              fontWeight: 700,
              color: "var(--warning)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            0.62
          </div>
        </div>
      </div>
    </div>
  );
}

function RegisterPanel(): ReactNode {
  return (
    <div className="panel-mock">
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--fg-3)", marginBottom: 10 }}>
        3 linhas para instrumentar
      </div>
      <pre
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 12.5,
          lineHeight: 1.6,
          color: "var(--fg-2)",
          background: "var(--surface-3)",
          border: "1px solid var(--border-subtle)",
          borderRadius: 8,
          padding: 14,
          margin: 0,
          whiteSpace: "pre-wrap",
        }}
      >
        <span style={{ color: "#c4a8ff" }}>import</span> evalops{"\n"}
        evalops.init(api_key=<span style={{ color: "#5fd5a4" }}>&quot;evk_prod_...&quot;</span>, project=
        <span style={{ color: "#5fd5a4" }}>&quot;docops-agent&quot;</span>){"\n\n"}
        <span style={{ color: "#ffb86b" }}>@evalops.trace</span>(name=
        <span style={{ color: "#5fd5a4" }}>&quot;rag.summarize&quot;</span>){"\n"}
        <span style={{ color: "#c4a8ff" }}>def</span>{" "}
        <span style={{ color: "#6db3ff" }}>summarize</span>(q, doc):{"\n"}    <span style={{ color: "#5a6791" }}>...</span>
      </pre>
      <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
        <span
          style={{
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 999,
            background: "var(--success-soft)",
            border: "1px solid var(--success-border)",
            color: "var(--success)",
          }}
        >
          &bull; Tracing ativo
        </span>
        <span
          style={{
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 999,
            background: "var(--accent-cyan-soft)",
            border: "1px solid rgba(34,211,238,0.32)",
            color: "var(--accent-cyan)",
          }}
        >
          &bull; Rubrica anexada
        </span>
        <span
          style={{
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 999,
            background: "var(--surface-2)",
            border: "1px solid var(--border-default)",
            color: "var(--fg-2)",
          }}
        >
          prod
        </span>
      </div>
    </div>
  );
}

export function AuthSidePanel({ variant }: Props) {
  return (
    <aside className="auth-side">
      {variant === "login" ? <LoginPanel /> : <RegisterPanel />}
      <div>
        {variant === "login" ? (
          <>
            <p className="auth-quote">
              Cada trace guarda a conversa, as ferramentas e o custo. Avalie com rubricas e leia a nota e o motivo
              de cada avaliador.
            </p>
            <p className="auth-attrib">
              <strong>EvalOps Studio</strong> &middot; traces, rubricas e quality gate para agentes LLM
            </p>
          </>
        ) : (
          <>
            <p className="auth-quote">
              Grátis durante o beta. Crie o workspace, gere uma chave e envie o primeiro trace pelo SDK Python.
            </p>
            <p className="auth-attrib">
              <strong>Plano Free:</strong> limites mensais de traces, avaliações e exports &middot; uso visível em
              Settings
            </p>
          </>
        )}
      </div>
    </aside>
  );
}


