import Link from "next/link";

export function MarketingFooter() {
  return (
    <footer className="mk-footer">
      <div className="mk-container">
        <div className="mk-footer__grid">
          <div className="mk-footer__brand">
            <Link href="/" className="mk-brand">
              <img src="/brand/mark-evalops.svg" alt="" />
              <span>
                EvalOps<span className="sub">Studio</span>
              </span>
            </Link>
            <p>
              A camada de observabilidade, governança e qualidade para aplicações de IA. Feito para
              engenheiros de IA que colocam agentes em produção.
            </p>
          </div>
          <div>
            <h5>Produto</h5>
            <ul>
              <li><a href="/#product">Rastreamento</a></li>
              <li><a href="/#product">Rubricas</a></li>
              <li><a href="/#product">Experimentos</a></li>
              <li><a href="/#product">Datasets</a></li>
              <li><Link href="/changelog">Changelog</Link></li>
            </ul>
          </div>
          <div>
            <h5>Desenvolvedores</h5>
            <ul>
              <li><Link href="/docs">Documentação</Link></li>
              <li><Link href="/docs">Python SDK</Link></li>
              <li><Link href="/docs">HTTP API</Link></li>
              <li>
                <a href="https://github.com/rouggerxavier/EvalOps" target="_blank" rel="noreferrer">
                  GitHub
                </a>
              </li>
            </ul>
          </div>
          <div>
            <h5>Empresa</h5>
            <ul>
              <li><Link href="/login">Entrar</Link></li>
              <li><Link href="/register">Criar espaço de trabalho</Link></li>
              <li><Link href="/app">Abrir app</Link></li>
            </ul>
          </div>
        </div>
        <div className="mk-footer__bottom">
          <span>&copy; 2026 EvalOps Studio &middot; Todos os horários em UTC</span>
          <span className="mk-footer__ops">Todos os sistemas operando</span>
        </div>
      </div>
    </footer>
  );
}
