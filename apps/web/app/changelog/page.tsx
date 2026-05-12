import { MarketingFooter } from "@/components/MarketingFooter";
import { MarketingNav } from "@/components/MarketingNav";

const entries = [
  {
    version: "0.7.0",
    date: "2026-04-29",
    notes: [
      "Phase 6 completed: feedback endpoints, JSONL export jobs, usage counters and quota mocks.",
      "Frontend coverage expanded for rubrics, evaluations, prompts, datasets, experiments and exports.",
      "O detalhe de trace agora suporta feedback humano inline.",
    ],
  },
  {
    version: "0.5.0",
    date: "2026-04-29",
    notes: [
      "Versionamento de prompts, datasets e experimentos foram introduzidos na API e no dashboard.",
      "Resumos de runs de experimento e comparações de variantes foram adicionados.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <div className="mk-shell">
      <div className="bg-stage"><div className="bg-grid" /></div>
      <MarketingNav />
      <main className="mk-wrap public-page">
        <section className="mk-section">
          <div className="mk-container">
            <span className="mk-eyebrow">Notas de versão</span>
            <h1 className="public-title">Changelog</h1>
            <p className="lede">Notas de versão for EvalOps Studio.</p>

            <div className="stack-list public-release-list">
              {entries.map((entry) => (
                <article key={entry.version} className="card public-release">
                  <div className="section-head">
                    <div>
                      <h2>{entry.version}</h2>
                      <p>{entry.date}</p>
                    </div>
                    <span className="badge badge--primary">Versão</span>
                  </div>
                  <ul>
                    {entry.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
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


