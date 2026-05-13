"use client";

import Link from "next/link";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { useState } from "react";

type FeatureStep = {
  title: string;
  subtitle: string;
  description: string;
  notes: string[];
  cta?: { href: string; label: string };
};

const FEATURE_STEPS: FeatureStep[] = [
  {
    title: "Tracing estruturado",
    subtitle: "Do user_message ao llm_response em uma trilha única.",
    description:
      "Veja cada execução em timeline com spans encadeados. O time encontra gargalos e custo sem navegar em telas soltas.",
    notes: ["Tokens por etapa", "Custo por chamada", "Latência fim a fim"],
  },
  {
    title: "Avaliações e rubricas",
    subtitle: "Qualidade declarada em critérios objetivos.",
    description:
      "Combine LLM-as-judge, regex e schema para avaliar resposta com score, motivo e status de aprovação.",
    notes: ["Relevância", "Fidelidade", "Segurança", "Correção"],
  },
  {
    title: "Experimentos e regressão",
    subtitle: "Compare versões antes do deploy.",
    description:
      "Rode conjuntos de teste entre variantes de prompt e modelo para enxergar delta de score, custo e latência em minutos.",
    notes: ["v0.6 vs v0.7", "Deltas positivos e negativos", "Gate de regressão"],
  },
  {
    title: "Deploy com segurança",
    subtitle: "Checklist claro antes de promover produção.",
    description:
      "Promova somente quando os quality gates fecharem. A decisão de release fica auditável e compartilhável.",
    notes: ["Rubrics passed", "No PII leak", "Latency within budget", "Quality gate approved"],
    cta: { href: "/docs", label: "Ver documentação" },
  },
];

const SECONDARY_CHIPS = ["Custo visível", "Feedback como dataset", "Privacidade por padrão", "Exportação"];

const stepVariants = {
  enter: (dir: number) => ({ x: dir >= 0 ? "82%" : "-82%", opacity: 0.45 }),
  center: { x: "0%", opacity: 1 },
  exit: (dir: number) => ({ x: dir >= 0 ? "-28%" : "28%", opacity: 0 }),
};

function previewForStep(stepIndex: number, notes: string[]) {
  if (stepIndex === 0) {
    return (
      <div className="evo-step-preview evo-step-preview--trace">
        {[
          ["user_message", "420 tokens", "$0.0012", "112ms"],
          ["retrieval", "8 chunks", "$0.0003", "86ms"],
          ["tool_call", "search_docs()", "$0.0001", "74ms"],
          ["llm_response", "768 tokens", "$0.0038", "412ms"],
        ].map((item) => (
          <div className="evo-trace-row" key={item[0]}>
            <strong>{item[0]}</strong>
            <span>{item[1]}</span>
            <span>{item[2]}</span>
            <span>{item[3]}</span>
          </div>
        ))}
      </div>
    );
  }

  if (stepIndex === 1) {
    return (
      <div className="evo-step-preview evo-step-preview--score">
        {[
          ["Relevância", "0.92"],
          ["Fidelidade", "0.89"],
          ["Segurança", "0.96"],
          ["Correção", "0.91"],
        ].map((item) => (
          <div className="evo-score-card" key={item[0]}>
            <span>{item[0]}</span>
            <strong>{item[1]}</strong>
          </div>
        ))}
        <p>rubricas.yaml + llm_judge + regex/schema</p>
      </div>
    );
  }

  if (stepIndex === 2) {
    return (
      <div className="evo-step-preview evo-step-preview--compare">
        <div className="evo-compare-head">
          <span>v0.6</span>
          <span>v0.7</span>
          <span>delta</span>
        </div>
        {[
          ["Score", "0.81", "0.88", "+8.6%"],
          ["Custo", "$18.40", "$13.42", "-27.1%"],
          ["Latência", "1.48s", "1.14s", "-340ms"],
          ["Regressoes", "5", "1", "-80%"],
        ].map((item) => (
          <div className="evo-compare-row" key={item[0]}>
            <strong>{item[0]}</strong>
            <span>{item[1]}</span>
            <span>{item[2]}</span>
            <span className={item[3].startsWith("-") ? "neg" : "pos"}>{item[3]}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="evo-step-preview evo-step-preview--check">
      {notes.map((note) => (
        <div className="evo-check-row" key={note}>
          <Check />
          <span>{note}</span>
        </div>
      ))}
      <div className="evo-check-actions">
        <Link className="mk-btn mk-btn--secondary" href="/register">
          Abrir dashboard
        </Link>
      </div>
    </div>
  );
}

type PanelProps = {
  stepIndex: number;
};

function StepPanel({ stepIndex }: PanelProps) {
  const step = FEATURE_STEPS[stepIndex];
  return (
    <div className="evo-step-panel">
      <div className="evo-step-panel__copy">
        <p className="evo-step-panel__kicker">Etapa {stepIndex + 1}</p>
        <h3>{step.title}</h3>
        <p className="evo-step-panel__subtitle">{step.subtitle}</p>
        <p>{step.description}</p>
        <ul>
          {step.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        {step.cta ? (
          <Link className="mk-btn mk-btn--secondary" href={step.cta.href}>
            {step.cta.label}
          </Link>
        ) : null}
      </div>
      <div className="evo-step-panel__preview">{previewForStep(stepIndex, step.notes)}</div>
    </div>
  );
}

export function EvalOpsFeatureStepper() {
  const [currentStep, setCurrentStep] = useState(0);
  const [direction, setDirection] = useState<1 | -1>(1);

  const isFirstStep = currentStep === 0;
  const isLastStep = currentStep === FEATURE_STEPS.length - 1;

  const goToStep = (index: number) => {
    if (index === currentStep || index < 0 || index >= FEATURE_STEPS.length) return;
    setDirection(index > currentStep ? 1 : -1);
    setCurrentStep(index);
  };

  return (
    <div className="evo-feature-stepper">
      <div className="evo-feature-stepper__shell">
        <div className="evo-feature-stepper__indicators" role="tablist" aria-label="Fluxo de publicação">
          {FEATURE_STEPS.map((step, index) => {
            const isActive = index === currentStep;
            const isComplete = index < currentStep;
            return (
              <button
                key={step.title}
                type="button"
                className={`evo-step-indicator${isActive ? " is-active" : ""}${isComplete ? " is-complete" : ""}`}
                onClick={() => goToStep(index)}
                role="tab"
                aria-selected={isActive}
                aria-label={`Etapa ${index + 1}: ${step.title}`}
              >
                <span className="evo-step-indicator__dot">{isComplete ? <Check size={12} /> : index + 1}</span>
                <span className="evo-step-indicator__label">{step.title}</span>
              </button>
            );
          })}
        </div>

        <div className="evo-feature-stepper__content">
          <MotionConfig reducedMotion="never">
            <AnimatePresence initial={false} mode="sync" custom={direction}>
              <motion.div
                key={currentStep}
                className="evo-step-motion-layer"
                custom={direction}
                variants={stepVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.24, ease: [0.25, 0.1, 0.25, 1] }}
              >
                <StepPanel stepIndex={currentStep} />
              </motion.div>
            </AnimatePresence>
          </MotionConfig>
        </div>

        <div className="evo-feature-stepper__footer">
          <button
            type="button"
            className="mk-btn mk-btn--ghost"
            onClick={() => goToStep(currentStep - 1)}
            disabled={isFirstStep}
              aria-label="Voltar etapa"
          >
            <ChevronLeft />
            Anterior
          </button>
          {isLastStep ? (
            <Link className="mk-btn mk-btn--primary" href="/register">
              Abrir dashboard
            </Link>
          ) : (
            <button
              type="button"
              className="mk-btn mk-btn--primary"
              onClick={() => goToStep(currentStep + 1)}
              aria-label="Próxima etapa"
            >
              Próximo
              <ChevronRight />
            </button>
          )}
        </div>
      </div>

      <div className="evo-feature-stepper__chips" aria-label="Recursos complementares">
        {SECONDARY_CHIPS.map((chip) => (
          <span key={chip}>{chip}</span>
        ))}
      </div>
    </div>
  );
}
