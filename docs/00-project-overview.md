# 00 — Project Overview

## 1. O que é o EvalOps Studio

**EvalOps Studio** é um mini-SaaS de **LLMOps / AgentOps** que oferece, em uma única plataforma:

1. **Tracing** estruturado de chamadas a LLMs e agentes (prompt, resposta, ferramentas, tokens, custo, latência, fallback, erro).
2. **Avaliação automática** das respostas (LLM-as-judge + heurísticas + métricas determinísticas) com rubricas configuráveis.
3. **Versionamento** de prompts e modelos com testes de regressão entre versões.
4. **Dashboards** de qualidade, custo, latência e falhas com drill-down até o trace individual.
5. **Feedback humano** (HITL) e **exportação de datasets** para fine-tuning, few-shot e evals offline.

A plataforma é instrumentada via **API HTTP** (qualquer linguagem) e via **SDK Python oficial** (`evalops-python`) com decorator `@trace`.

## 2. Problema que resolve

Equipes que constroem com LLMs/agentes enfrentam um conjunto de problemas operacionais que não são resolvidos por ferramentas tradicionais de APM:

| Problema | Por que ferramentas comuns não resolvem |
|---|---|
| **Não dá para "testar" um LLM como se testa código** | Saídas não-determinísticas; testes unitários falham aleatoriamente |
| **Custo invisível** | Tokens variam por chamada; sem agregação por feature/usuário/prompt-version |
| **Regressão silenciosa ao trocar modelo/prompt** | Nada quebra "tecnicamente"; qualidade cai sem alarme |
| **Sem rubrica padronizada de qualidade** | Cada projeto reinventa "está bom?" |
| **Feedback do usuário não vira dataset** | Não há pipeline pronto para coletar 👍/👎 e exportar para FT |
| **Trace de agente é multi-step** | APMs assumem 1 request → 1 response; agentes têm árvore de chamadas |

EvalOps Studio é a resposta integrada para esses problemas em um único produto, focado em **DX excelente para AI engineers** (poucas linhas para instrumentar, rubricas em YAML, comparação de versões em uma tela).

## 3. Para quem é

- **AI Engineers** instrumentando agentes em produção.
- **Tech leads** que precisam justificar troca de modelo (custo vs. qualidade).
- **PMs de produtos com IA** que querem saber qualidade real percebida.
- **Pessoas em transição para AI Engineering** (público de portfólio) que precisam estudar LLMOps na prática.

Personas detalhadas em [`02-user-personas-and-use-cases.md`](02-user-personas-and-use-cases.md).

## 4. Casos de uso âncora

1. **DocOps Agent** instrumentado: cada sumarização e cada flashcard gerado tem trace + eval automático de "fidelidade ao documento". Dashboard mostra custo por usuário e qualidade por tipo de documento.
2. **Agente ImobiliarIA**: cada interação de triagem é avaliada (rubrica: "captou intenção?", "respondeu sem alucinar dados de imóvel?"). Quando score cai abaixo de 0.7, gera alerta e vai para fila de revisão humana.
3. **Aurora Support AI**: regression test suite roda a cada deploy; se `gpt-4o-mini` não baterem 95% dos casos do golden-set, deploy é bloqueado em CI.
4. **Comparação de providers**: rodar a mesma rubrica em OpenAI, Gemini e Groq lado a lado, com custo e latência por chamada, e decidir.

## 5. Valor para portfólio

EvalOps Studio é o único projeto do portfólio que demonstra:

- Domínio de **LLMOps/AgentOps** como disciplina (não só "saber chamar a API da OpenAI").
- Capacidade de projetar uma **plataforma multi-tenant** com auth real, API keys, RBAC.
- Domínio de **arquitetura assíncrona** (workers, fila, idempotência, backpressure).
- Domínio de **dados estruturados em escala** (modelagem de traces, índices, particionamento).
- Capacidade de construir **SDK** (DX), não só consumir API alheia.
- Ponte entre **engineering** (código bonito) e **produto** (dashboard que vende).

Detalhes em [`18-portfolio-positioning.md`](18-portfolio-positioning.md).

## 6. O que **não** é

- Não é um substituto de APM (Datadog, NewRelic) para latência/erros de infra geral.
- Não é uma plataforma de fine-tuning (mas exporta datasets para uma).
- Não é um framework de agentes (instrumenta agentes feitos em LangGraph, CrewAI, AutoGen, custom).
- Não é um marketplace de prompts. Versionamento é interno ao projeto.

## 7. Princípios de produto

1. **DX first.** Instrumentar deve custar 3 linhas, não 30.
2. **Rubrica como código.** Avaliação é YAML versionado, não config em UI.
3. **Custo visível por padrão.** Toda chamada mostra USD estimado, não só tokens.
4. **Sem vendor lock-in.** Abstração de provider via `litellm`; export aberto em JSONL.
5. **Privacy by default no schema.** Mesmo com redaction off no MVP, todas as colunas estão prontas para masking.
6. **Sob teste o tempo todo.** O próprio engine de eval tem "evals dos evals" (meta-evals).

## 8. Premissas explícitas

- O autor terá ≥1 dos seus projetos (DocOps, ImobiliarIA, Aurora) instrumentado como demo real até o fim do MVP — isso vira o screenshot principal do portfólio.
- O custo de LLM para evals durante desenvolvimento será limitado a **USD 50/mês** via combinação de Groq + cache + rubricas pequenas. Caso ultrapasse, evals usam apenas heurísticas determinísticas.
- O projeto não armazena dados de produção sensíveis de clientes reais nesta fase. Dados de teste são sintéticos ou redatados.
- O autor implementará sozinho, em ~6-10 semanas de trabalho focado, então o escopo do MVP precisa ser cirurgicamente cortado (ver [03](03-mvp-scope.md)).

## 9. Glossário rápido

| Termo | Significado |
|---|---|
| **Trace** | Registro completo de uma "execução" de IA (1 chamada simples ou árvore multi-step) |
| **Span** | Um nó dentro de um trace (uma chamada LLM, uma tool call, um retrieve) |
| **Event** | Marcador pontual dentro de um span (e.g., "fallback acionado") |
| **Rubric** | Definição declarativa de critérios de avaliação (YAML) |
| **Evaluator** | Implementação que aplica uma rubrica e retorna score(s) |
| **Run** | Execução de um evaluator sobre um trace ou conjunto de traces |
| **Experiment** | Comparação controlada entre versões de prompt/modelo sobre o mesmo dataset |
| **Golden set** | Conjunto curado de inputs com saídas esperadas para regression |
| **HITL** | Human-in-the-loop — feedback ou anotação humana |
