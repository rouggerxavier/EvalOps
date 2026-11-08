# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: AI engineers who keep LLM apps and agents running in production. They open EvalOps to find what broke, why, and what it cost, then drill into a single trace.

Secondary: people with no engineering background who only want to know whether the AI is doing what it should. They must be able to answer that from the main screens without knowing what a span, p95 or rubric is.

## Product Purpose

EvalOps Studio records every run of an AI system as a trace and evaluates it against written rubrics. Success: anyone opening a project learns right away what needs attention, and an engineer reaches the responsible trace in one step.

## Positioning

Tracing and evaluation live in one product: the same run that shows latency and cost also carries a verdict on whether the AI did what it was supposed to do.

## Operating Context

Ingestion comes through the `evalops-python` SDK and API keys, per environment (dev, staging, prod). Work happens in an organization > project hierarchy. Rubrics are written in YAML, and judges are LLM or heuristic. Keyboard shortcuts (G + letter) navigate the app.

## Capabilities and Constraints

Screens: overview, traces (list, detail, compare), evaluations, prompts, rubrics, datasets, experiments, API keys, exports, settings, plus login, register, landing, docs, changelog and health.

Stack: Next.js App Router, Server Components and Server Actions, plain CSS, `lucide-react` and `motion`. No Tailwind, no shadcn, no CSS-in-JS. UI language is pt-BR.

Trace statuses: `ok`, `partial`, `error`. Redacted traces must stay visibly marked. Cost may be `priced`, `provided`, `unpriced` or `unknown`, and those must not be presented as equivalent.

## Brand Commitments

Name: EvalOps Studio. No logo or visual identity is binding: the user asked for the current look to be replaced because it is ugly and visually polluted.

## Evidence on Hand

No customers, testimonials, benchmarks or public pricing are on hand. Future work must not fabricate them.

## Product Principles

1. The first question is always "what needs attention?"; everything else is one level down.
2. Every technical number has a plain-language reading next to it, and experts can still reach the raw value.
3. One screen, one job: remove anything that does not serve that job.
4. A verdict always links to its evidence: the trace, the rubric, the score.
