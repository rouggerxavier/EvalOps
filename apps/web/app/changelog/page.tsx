const entries = [
  {
    version: "0.7.0",
    date: "2026-04-29",
    notes: [
      "Phase 6 completed: feedback endpoints, JSONL export jobs, usage counters and quota mocks.",
      "Frontend coverage expanded for rubrics, evaluations, prompts, datasets, experiments and exports.",
      "Trace detail now supports inline human feedback.",
    ],
  },
  {
    version: "0.5.0",
    date: "2026-04-29",
    notes: [
      "Prompt versioning, datasets and experiments introduced in API and dashboard.",
      "Experiment run summaries and variant comparisons added.",
    ],
  },
];

export default function ChangelogPage() {
  return (
    <main className="container">
      <div className="panel">
        <h1 style={{ marginTop: 0 }}>Changelog</h1>
        {entries.map((entry) => (
          <section key={entry.version} style={{ marginBottom: 16 }}>
            <h2 style={{ marginBottom: 6 }}>
              {entry.version} <span className="muted">({entry.date})</span>
            </h2>
            <ul style={{ marginTop: 0 }}>
              {entry.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}
