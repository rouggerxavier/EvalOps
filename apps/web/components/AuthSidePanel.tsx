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
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--fg-3)" }}>2m ago</span>
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
        Summarize the Q4 earnings deck and surface any guidance change.
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
        Revenue +14% YoY. Op-margin held. Guidance lifted: FY net-income range now $4.8&ndash;5.2B (was
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
          <div style={{ fontSize: 10, color: "var(--success)" }}>Groundedness</div>
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
          <div style={{ fontSize: 10, color: "var(--success)" }}>Helpfulness</div>
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
        3 lines to instrument
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
        evalops.init(api_key=<span style={{ color: "#5fd5a4" }}>&quot;evk_live_…&quot;</span>, project=
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
          &bull; Tracing live
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
          &bull; Rubric attached
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
              EvalOps gave us drift detection and cost-per-feature in the same week we plugged it in. We
              stopped flying blind on agent quality.
            </p>
            <p className="auth-attrib">
              <strong>Maya Halil</strong> &middot; Staff AI Engineer, DocOps Agent
            </p>
          </>
        ) : (
          <>
            <p className="auth-quote">
              Free during beta. Generous limits. Self-host when you outgrow us &mdash; your data, your call.
            </p>
            <p className="auth-attrib">
              <strong>Included:</strong> 1M traces/month &middot; unlimited rubrics &middot; 5 team members
              &middot; 90-day retention
            </p>
          </>
        )}
      </div>
    </aside>
  );
}
