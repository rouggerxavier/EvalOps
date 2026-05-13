import styles from "./HowItWorksPipeline.module.css";

type PipelineStep = {
  step: string;
  title: string;
  body: string;
  previewTitle: string;
  previewLines: string[];
  tone: "trace" | "eval" | "compare" | "ship";
};

const PIPELINE_STEPS: PipelineStep[] = [
  {
    step: "ETAPA 01",
    title: "Instrumente",
    body: "Adicione o SDK ou envie traces por POST diretamente. Spans, ferramentas e eventos entram em um único grafo de execução.",
    previewTitle: "Entrada",
    previewLines: ["POST /agent/run", "evalops.trace(...)"],
    tone: "trace",
  },
  {
    step: "ETAPA 02",
    title: "Avalie",
    body: "Rode rubricas na ingestão ou manualmente. Cada trace recebe score, reasoning e status de aprovação.",
    previewTitle: "Rubric",
    previewLines: ["Score 0.86", "Rubric passed"],
    tone: "eval",
  },
  {
    step: "ETAPA 03",
    title: "Compare",
    body: "Rode experimentos entre prompts, modelos ou parâmetros e compare qualidade, custo e latência.",
    previewTitle: "Delta",
    previewLines: ["v1.7.1 -> v1.7.2", "+6.2% score", "-12% latency"],
    tone: "compare",
  },
  {
    step: "ETAPA 04",
    title: "Melhore",
    body: "Promova a melhor variante e exporte exemplos de alta qualidade para fine-tuning ou suítes de regressão.",
    previewTitle: "Gate",
    previewLines: ["Quality gate passed", "0 critical regressions", "Ready to deploy"],
    tone: "ship",
  },
];

export function HowItWorksPipeline() {
  return (
    <div className={styles.howPipelineRoot}>
      <p className={styles.howPipelineIntro}>
        Capture traces reais, rode avaliações, compare versões e aprove apenas mudanças seguras.
      </p>
      <div className={styles.howPipelineTrack} aria-label="Pipeline de observabilidade e deploy">
        {PIPELINE_STEPS.map((item) => (
          <article key={item.step} className={styles.howPipelineCard}>
            <div className={styles.howPipelineTop}>
              <span className={styles.howPipelineStep}>{item.step}</span>
              <span className={`${styles.howPipelineDot} ${styles[`is${item.tone[0].toUpperCase()}${item.tone.slice(1)}`]}`} />
            </div>
            <h4>{item.title}</h4>
            <p>{item.body}</p>
            <div className={styles.howPipelinePreview}>
              <span className={styles.howPipelinePreviewTitle}>{item.previewTitle}</span>
              <div className={styles.howPipelinePreviewLines}>
                {item.previewLines.map((line) => (
                  <span key={line}>{line}</span>
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

