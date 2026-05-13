import Link from "next/link";
import { ArrowRight } from "lucide-react";

import styles from "./FinalLandingCta.module.css";

export function FinalLandingCta() {
  return (
    <div className={styles.finalCtaRoot}>
      <span className={styles.finalCtaBadge}>PRONTO PARA COMEÇAR</span>
      <h2>Pare de debugar seu agente por screenshots.</h2>
      <p>
        Crie um projeto, conecte o SDK e veja seus primeiros traces avaliados fluindo em menos de cinco minutos.
      </p>

      <div className={styles.finalCtaActions}>
        <Link className="mk-btn mk-btn--primary mk-btn--lg" href="/register">
          Crie seu workspace
          <ArrowRight />
        </Link>
        <Link className="mk-btn mk-btn--secondary mk-btn--lg" href="/login">
          Entrar
        </Link>
      </div>

      <div className={styles.finalCtaMeta} aria-label="Benefícios de onboarding">
        <span>Sem cartão de crédito</span>
        <span>Setup em &lt; 5 min</span>
        <span>SDK + dashboard</span>
      </div>

      <div className={styles.finalCtaFloaters} aria-hidden="true">
        <span className={styles.floaterOne}>trace captured</span>
        <span className={styles.floaterTwo}>eval passed</span>
      </div>
    </div>
  );
}
