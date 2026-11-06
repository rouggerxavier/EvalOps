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
    body: "Adicione o SDK Python ou envie traces por POST. Conversa, ferramentas, modelo e custo ficam no mesmo trace.",
    previewTitle: "Entrada",
    previewLines: ["@evalops.trace(...)", "span.set_llm(...)"],
    tone: "trace",
  },
  {
    step: "ETAPA 02",
    title: "Avalie",
    body: "Escolha os traces e rode uma rubrica pela tela ou pela API. Cada avaliação traz nota, motivo e aprovação por avaliador.",
    previewTitle: "Rubrica",
    previewLines: ["Nota 0.86", "Rubrica aprovada"],
    tone: "eval",
  },
  {
    step: "ETAPA 03",
    title: "Verifique",
    body: "Defina no quality gate a nota mínima e os limites de custo e latência p95. Ele compara a janela de traces com esses limites.",
    previewTitle: "Gate",
    previewLines: ["Nota média 0.86 >= 0.80", "p95 1.2s <= 2s", "Status: pass"],
    tone: "compare",
  },
  {
    step: "ETAPA 04",
    title: "Exporte",
    body: "Exporte traces com o feedback humano em JSONL para montar suas suítes de regressão.",
    previewTitle: "Export",
    previewLines: ["traces.jsonl", "feedback incluído"],
    tone: "ship",
  },
];

export function HowItWorksPipeline() {
  return (
    <div className={styles.howPipelineRoot}>
      <p className={styles.howPipelineIntro}>
        Capture traces reais, avalie com rubricas e confira o projeto contra os limites de qualidade.
      </p>
      <div className={styles.howPipelineTrack} aria-label="Como o EvalOps funciona">
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

