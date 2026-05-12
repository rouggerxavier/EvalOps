import Link from "next/link";

type Props = {
  layout?: "main" | "container";
};

export function AuthRequiredPanel({ layout = "main" }: Props) {
  const shellClass = layout === "container" ? "container" : "main";

  return (
    <main className={shellClass}>
      <div className="card auth-required-card">
        <div className="section-head">
          <div>
            <h2>Autenticação necessária</h2>
            <p>Entre para acessar o dashboard deste projeto.</p>
          </div>
        </div>
        <div className="actions-row">
          <Link className="primary-btn" href="/login">
            Entrar
          </Link>
          <Link className="subtle-link" href="/register">
            Criar conta
          </Link>
        </div>
      </div>
    </main>
  );
}


