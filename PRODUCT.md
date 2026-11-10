# Product

<!-- impeccable:product-schema 1 -->

## Platform

Web SaaS, com API HTTP, SDK Python e CLI para avaliação offline e investigações. MCP permanece proposto.

## Users

Engenheiros de IA, ML e software que investigam falhas, comparam versões e decidem se uma mudança pode avançar. Revisores humanos precisam compreender evidências e riscos sem dominar detalhes de tracing. Agentes de programação são usuários programáticos com identidade, permissões e limites explícitos; não substituem revisão humana.

## Product Purpose

EvalOps Studio evolui para uma plataforma de avaliação, experimentação, observabilidade e qualidade de sistemas de IA, operada por humanos e agentes sobre as mesmas entidades, métricas e evidências.

**Hoje:** tracing e avaliação de aplicações generativas/agentes, rubricas, feedback, Quality Gate e workflows de prompts/datasets. Experimentos legados sintetizam respostas; replay repete uma chamada LLM. As verticais tabulares avaliam predições importadas de regressão e classificação, com snapshots imutáveis, versões declaradas, métricas tipadas e comparação pareada descritiva. Investigações e curadoria preservam autoria e revisão humana. Não executa agente completo.

**Proposta restante:** outras tarefas de ML/DL, artefatos e runners de aplicações reais. As SPECs preservam os contratos de referência; o [registro de execução](docs/plans/autonomous-evolution.md) separa implementação de evidência externa pendente.

## Positioning

Especialização proposta: transformar observações e avaliações em decisões de qualidade rastreáveis, com linguagem acessível e evidência técnica compartilhada. Complementar tracking/registry externos em vez de substituir MLflow/W&B ou criar plataforma de treinamento. AI-first significa operação programática completa; a interface web continua central. Não exige chatbot, terminal ou agente de IA para trabalho humano.

O diferencial entre famílias de tarefas é hipótese a validar, não vantagem comercial comprovada. Ver [pesquisa](docs/architecture/referencias-2026-11-09.md) e [roadmap](docs/plans/roadmap-evolucao.md).

## Operating Context

Hoje: organização > projeto, ambientes dev/staging/prod, ingestão SDK/chaves, usuários com memberships organizacionais. Chaves legadas têm ingest/read/evaluate. Principais de serviço usam chaves com identidade, projeto, ambiente e read/write/evaluate nas novas superfícies; rotas legadas sem autorização equivalente permanecem restritas. Rubricas YAML e avaliadores determinísticos/judge. Web usa Next.js, Server Components/Actions e API FastAPI; português brasileiro.

Web/API/SDK/CLI compartilham resultados persistidos nas novas tarefas e investigações. MCP futuro deverá usar o mesmo núcleo. Modelos clássicos e redes são avaliados pela tarefa, não por simulação de mensagens LLM. Execução externa depende de manifest, fixtures, permissões e limites.

## Capabilities and Constraints

Telas atuais: overview, traces/detalhe/compare, evaluations, regressão offline/comparação, investigações, falhas observadas, curadoria de casos, prompts, rubrics, datasets, experiments, keys, exports, settings e conta. [Auditoria por capacidade](docs/audits/estado-real-2026-11-09.md) distingue implementado, parcial, documentação e proposta.

Stack preservada: Next.js App Router, CSS puro, lucide-react e motion; sem Tailwind/shadcn/CSS-in-JS. Fonte visual atual: [DESIGN.md](DESIGN.md). Preservar identidade e shell; novas tarefas precisam visualizações próprias, como resíduos e matriz de confusão.

Ingestão, execução e qualidade são estados separados. Trace `ok/partial/error` não prova qualidade. Custos `priced/provided/unpriced/unknown` não são equivalentes. Ausência de medida nunca vira zero. Juiz pode errar; falta de evidência pode tornar resultado inconclusivo.

## Brand Commitments

Nome EvalOps Studio. Manter sistema visual atual quando adequado. Nenhum redesign completo integra este plano. Clareza, evidência e controle humano prevalecem sobre aparência de automação.

## Evidence on Hand

Auditoria inicial em main `545149b`; F0/F1 integradas pelo PR #47 (`124aa18`). Testes de contrato, migrations SQLite/PostgreSQL, concorrência e E2E sustentam as entregas; consulte o registro de execução para resultados por fase. Grankasa fornece caso sintético integrado e relatório de modelo real em branch local separada; não é validação geral de qualidade nem dependência de domínio. Não há benchmark comercial, clientes/testemunhos ou preços públicos validados nesta etapa.

## Product Principles

1. Humanos e agentes compartilham dados, resultados e regras; interfaces diferem conforme capacidade de uso.
2. A web permite operações centrais sem terminal ou IA.
3. Cada decisão aponta para evidência, método, versões e limitações.
4. Tarefa determina métrica; arquitetura do modelo não obriga abstração LLM.
5. Avaliação offline, execução de modelo, replay LLM e execução de agente são capacidades distintas.
6. Custo, efeitos externos e privacidade são controlados no servidor e no runner.
7. Segurança e estados incertos não dependem da obediência de um prompt.
8. Começar com regressão offline limitada; ampliar após valor demonstrado.

## Scope and Exclusions

Primeira vertical: predições numéricas importadas de regressão, snapshot, modelo/versão declarado, MAE/MSE/RMSE/R², resíduos, comparação descritiva e web/API/SDK/CLI equivalentes. Não treina, hospeda ou carrega modelo executável. Não promete equivalência estatística ou superioridade de produto.

Depois: runner externo, piloto agêntico e DL por tarefa. Excluídos: treino distribuído, serving, GPU scheduler, registry completo, deploy automático e suporte simultâneo a todos os algoritmos.
