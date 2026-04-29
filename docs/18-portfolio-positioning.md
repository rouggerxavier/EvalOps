# 18 — Portfolio Positioning

Como apresentar o EvalOps Studio para o público que importa: **recrutadores AI Eng / Tech Leads / CTOs**.

## 1. O pitch em 30 segundos

> "EvalOps Studio é um mini-SaaS de LLMOps que construí para servir de camada de tracing, avaliação automática e versionamento sobre meus outros projetos com IA (DocOps, Aurora, ImobiliarIA). Ele resolve o problema de que **trocar prompt ou modelo costuma derrubar qualidade silenciosamente** — e nada testa isso. Tem ingestion via SDK Python (3 linhas), rubricas YAML versionadas, regression test em CI, dashboard de custo/qualidade. Stack: FastAPI, Next.js, Postgres, Redis, deploy em Vercel + Fly.io."

## 2. Como ele se encaixa no portfólio

| Projeto | Camada de exposição |
|---|---|
| **DocOps Agent** | Produto full-stack com IA + RAG + UX |
| **Aurora Support AI** | Fine-tuning, guardrails, datasets |
| **Agente ImobiliarIA** | Agente conversacional aplicado a negócio |
| **EvalOps Studio** ← novo | **Plataforma de operação** dos demais |

A narrativa: "construo apps com IA **e** sei operá-los em produção." Esse é exatamente o gap que separa "AI hobbyist" de "AI Engineer".

## 3. Posicionamento explícito vs concorrentes

EvalOps **não compete** comercialmente com LangSmith / Langfuse / Phoenix / Helicone — compete com **a versão sua deles que você teria que escrever de qualquer jeito quando subir IA em produção sem orçamento para SaaS pago**.

Mensagem para entrevista:
- _"Conheço LangSmith, Langfuse e Phoenix. Para entender de verdade o que essas ferramentas fazem, decidi construir uma versão minha — multi-tenant, com rubric-as-code, regression em CI. Aprendi muito sobre os tradeoffs."_

Esse enquadramento é honesto e remove ansiedade de comparação injusta.

## 4. Audiência-alvo

- **Recrutadores de AI Eng / ML Eng** em produtos com LLM em produção (fintechs, healthtech, customer-facing AI).
- **Tech leads** avaliando nível de senioridade.
- **Comunidade técnica** (LinkedIn, Twitter/X, Discord LangChain/LlamaIndex, fórum HN Show).

## 5. Conteúdo que vou produzir junto com o MVP

### 5.1 Vídeo demo (90s)
Roteiro:
1. (5s) "Quanto está custando a IA do seu produto e como você sabe se está bom?"
2. (10s) Tela do EvalOps mostrando 3 projetos instrumentados.
3. (15s) Instrumentação ao vivo do DocOps em < 1 min.
4. (15s) Trace aparecendo, click → detalhe + score.
5. (15s) Comparação Gemini vs OpenAI mesmo input — mostra delta de custo e qualidade.
6. (10s) Regression test em GitHub Actions falhando porque novo prompt regrediu.
7. (10s) "Stack: FastAPI + Next.js. Tudo aberto em github.com/.../EvalOps."
8. (10s) Outro: outros projetos do portfólio.

### 5.2 Post LinkedIn / blog
- "Como construí meu próprio LangSmith em 8 semanas — e o que aprendi sobre LLMOps"
- 3-5 screenshots fortes
- 3 lições não-óbvias (ex.: "rubric YAML > rubric UI", "judge cache reduz 70% custo", "trace+span+event > flat events")
- CTA: GitHub + vídeo

### 5.3 Documentação visível
- README do repositório com screenshots, badges, stack diagram, link para `/docs`.
- Site `docs.evalops.studio` (GitHub Pages).
- Página `/changelog` mostrando disciplina de release.

### 5.4 Demo dataset público
- Sample anonimizado de 500 traces do uso real (DocOps com prompts redatados) disponível em `examples/sample-trace-set.jsonl`. Mostra dimensão real, não brinquedo.

## 6. O que medir para validar o posicionamento

| Métrica | Alvo MVP | Alvo 90 dias |
|---|---|---|
| ⭐ no GitHub | 50 | 200+ |
| Posts orgânicos LinkedIn views | 5k | 30k |
| Cliques no demo deploy | 200 | 2k |
| Recrutadores fazendo follow-up no perfil | 5 | 20 |
| Mensagens "construí algo parecido" | 3 | 10 |

> Métricas de portfólio são proxy de "consegui chamar atenção qualificada". Não são north-star — but são honest signals.

## 7. Mensagem-chave por persona-recrutador

### Para CTO de fintech (LLMOps em compliance-heavy)
> "Schema privacy-aware desde o dia 1, audit log, redaction policy, RLS em Postgres. Mostro que entendo os requisitos de compliance que você teria com o vendor SaaS — e o que você teria que construir se quisesse self-hosted."

### Para Head of AI de scaleup
> "Regression em CI bloqueia deploy que regride qualidade. Cost breakdown por feature/usuário. É a primeira coisa que você implementa quando AI vira produto, não experimento."

### Para staff engineer
> "Decisões com motivo: ULID vs UUID, RLS como defense-in-depth, dataclasses no SDK para não conflitar com pydantic v1 do cliente, trace+span+event vs flat events. Cada ADR explicando o porquê."

## 8. Anti-pitch (cuidados)

- **Não** dizer "concorrente de Datadog/LangSmith". Soa pretensioso. Dizer "estudo construído sobre os mesmos problemas".
- **Não** prometer SLAs ou multi-tenant enterprise se não tem.
- **Não** publicar o domínio público antes do MVP estar polido (semana 7).

## 9. Roteiro de "o que mostrar primeiro" em entrevista

1. **Abrir o dashboard com dados reais** dos seus 3 projetos. Visível, vivo.
2. **Click em um trace** com fallback acionado. Mostrar árvore de spans + custo + score.
3. **Mostrar uma rubrica YAML.** Explicar trade-off llm_judge vs heurística.
4. **Mostrar um experiment** comparando 2 modelos. Decisão técnica explicada.
5. **Abrir um ADR.** Mostrar disciplina de decisão com motivos.
6. **Abrir o `tests/` e mostrar 1 teste de multi-tenancy** + 1 teste de evaluator. Mostra rigor.
7. **Falar do roadmap.** "Hoje é síncrono inline; semana 8 vira Arq porque [razão técnica]."

## 10. Definição de "portfólio done"

- [ ] Repositório público com README profissional + screenshots.
- [ ] Deploy hosted estável + 1 dos projetos do autor instrumentado, gerando dados reais por ≥ 2 semanas.
- [ ] Vídeo de 90s no perfil do LinkedIn.
- [ ] 1 post longo explicando 3 decisões técnicas não-óbvias.
- [ ] `/docs` viva e referenciada no README.
- [ ] Roadmap visível e honesto (mostra Fase 2 e 3).
- [ ] Pelo menos 1 PR de "outro humano" no histórico (mesmo que pequeno) — sinaliza colaboração.
