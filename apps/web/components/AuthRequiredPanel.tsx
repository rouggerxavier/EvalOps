import Link from "next/link";

type Props = {
  layout?: "main" | "container";
};

export function AuthRequiredPanel({ layout = "main" }: Props) {
  const shellClass = layout === "container" ? "container" : "main";
  const panelClass = layout === "container" ? "panel" : "card";

  return (
    <main className={shellClass}>
      <div className={panelClass} style={{ maxWidth: 560, padding: 20 }}>
        <h2 style={{ margin: "0 0 8px" }}>Acesso restrito</h2>
        <p className="muted" style={{ margin: "0 0 14px" }}>
          Faca login para acessar o dashboard deste projeto.
        </p>
        <div className="row" style={{ gap: 10 }}>
          <Link href="/login">Entrar</Link>
          <Link href="/register">Criar conta</Link>
        </div>
      </div>
    </main>
  );
}
