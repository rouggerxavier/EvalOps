import styles from "@/app/publicMarketingPages.module.css";
import LightPillar from "@/components/LightPillar";
import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";

const entries = [
  {
    version: "0.7.0",
    date: "2026-04-29",
    notes: [
      "Fase 6 conclu\u00EDda: endpoints de feedback, jobs de exporta\u00E7\u00E3o JSONL, contadores de uso e mocks de quota.",
      "Cobertura do frontend ampliada para rubrics, evaluations, prompts, datasets, experiments e exports.",
      "O detalhe de trace agora suporta feedback humano inline.",
    ],
  },
  {
    version: "0.5.0",
    date: "2026-04-29",
    notes: [
      "Versionamento de prompts, datasets e experimentos introduzido na API e no dashboard.",
      "Resumos de runs de experimento e compara\u00E7\u00F5es de variantes foram adicionados.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="mk-shell">
      <div className="bg-stage">
        <div className="bg-pillar" aria-hidden="true">
          <LightPillar
            topColor="#5aa3ff"
            bottomColor="#1a2a7a"
            intensity={1.0}
            rotationSpeed={0.16}
            glowAmount={0.0075}
            pillarWidth={2.8}
            pillarHeight={0.33}
            noiseIntensity={0.5}
            pillarRotation={130}
            interactive={false}
            mixBlendMode="screen"
            quality="medium"
          />
        </div>
        <div className="bg-grid" />
      </div>
      <MarketingNav />
      <main className={`mk-wrap ${styles.publicMain}`}>
        <section className={`mk-section ${styles.pageSection}`}>
          <div className={`mk-container ${styles.pageContainer}`}>
            <header className={styles.heroBlock}>
              <span className={`mk-eyebrow ${styles.eyebrow}`}>{"Notas de vers\u00E3o"}</span>
              <h1 className={styles.title}>Changelog</h1>
              <p className={styles.subtitle}>
                {"Hist\u00F3rico oficial de mudan\u00E7as do EvalOps Studio com novidades de plataforma, API e dashboard."}
              </p>
            </header>

            <div className={styles.releaseTimeline}>
              {entries.map((entry) => (
                <article key={entry.version} className={styles.releaseItem}>
                  <div className={styles.releaseCard}>
                    <div className={styles.releaseHead}>
                      <div>
                        <h2 className={styles.releaseVersion}>{entry.version}</h2>
                        <p className={styles.releaseDate}>{entry.date}</p>
                      </div>
                      <span className={styles.releaseBadge}>{"Vers\u00E3o"}</span>
                    </div>
                    <ul className={styles.releaseNotes}>
                      {entry.notes.map((note) => (
                        <li key={note} className={styles.releaseNote}>
                          {note}
                        </li>
                      ))}
                    </ul>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
        <MarketingFooter />
      </main>
    </div>
  );
}
