# Product

<!-- impeccable:product-schema 1 -->

## Platform

Web SaaS, com API HTTP e SDK Python. CLI e MCP são evolução proposta, ainda não implementada.

## Users

Engenheiros de IA, ML e software que investigam falhas, comparam versões e decidem se uma mudança pode avançar. Revisores humanos precisam compreender evidências e riscos sem dominar detalhes de tracing. Agentes de programação são usuários programáticos com identidade, permissões e limites explícitos; não substituem revisão humana.

## Product Purpose

EvalOps Studio evolui para uma plataforma de avaliação, experimentação, observabilidade e qualidade de sistemas de IA, operada por humanos e agentes sobre as mesmas entidades, métricas e evidências.

**Hoje:** tracing e avaliação de aplicações generativas/agentes, rubricas, feedback, Quality Gate e workflows de prompts/datasets. Experimentos atuais sintetizam respostas; replay repete uma chamada LLM. Não executa agente completo nem avalia ML tabular nativamente.

**Proposta:** avaliação por tarefa para ML tradicional e DL, snapshots imutáveis, métricas tipadas, comparação reproduzível e runners de aplicações reais. Nenhum desses contratos novos está entregue por esta revisão documental.

## Positioning

Especialização proposta: transformar observações e avaliações em decisões de qualidade rastreáveis, com linguagem acessível e evidência técnica compartilhada. Complementar tracking/registry externos em vez de substituir MLflow/W&B ou criar plataforma de treinamento. AI-first significa operação programática completa; a interface web continua central. Não exige chatbot, terminal ou agente de IA para trabalho humano.

O diferencial entre famílias de tarefas é hipótese a validar, não vantagem comercial comprovada. Ver [pesquisa](docs/architecture/referencias-2026-11-09.md) e [roadmap](docs/plans/roadmap-evolucao.md).

## Operating Context

Hoje: organização > projeto, ambientes dev/staging/prod, ingestão SDK/chaves, usuários com memberships organizacionais. Chaves têm ingest/read/evaluate, mas ainda não cobrem todas as operações. Rubricas YAML e avaliadores determinísticos/judge. Web usa Next.js, Server Components/Actions e API FastAPI; português brasileiro.

Futuro: mesmo núcleo atende web/API/SDK/CLI/MCP, sem regras paralelas. Modelos clássicos e redes são avaliados pela tarefa, não por simulação de mensagens LLM. Execução externa depende de manifest, fixtures, permissões e limites.

## Capabilities and Constraints

Telas atuais: overview, traces/detalhe/compare, evaluations, prompts, rubrics, datasets, experiments, keys, exports, settings e conta. [Auditoria por capacidade](docs/audits/estado-real-2026-11-09.md) distingue implementado, parcial, documentação e proposta.

Stack preservada: Next.js App Router, CSS puro, lucide-react e motion; sem Tailwind/shadcn/CSS-in-JS. Fonte visual atual: [DESIGN.md](DESIGN.md). Preservar identidade e shell; novas tarefas precisam visualizações próprias, como resíduos e matriz de confusão.

Ingestão, execução e qualidade são estados separados. Trace `ok/partial/error` não prova qualidade. Custos `priced/provided/unpriced/unknown` não são equivalentes. Ausência de medida nunca vira zero. Juiz pode errar; falta de evidência pode tornar resultado inconclusivo.

## Brand Commitments

Nome EvalOps Studio. Manter sistema visual atual quando adequado. Nenhum redesign completo integra este plano. Clareza, evidência e controle humano prevalecem sobre aparência de automação.

## Evidence on Hand

Código auditado em main `545149b`, testes existentes e históricos datados. Grankasa fornece caso sintético integrado e relatório de modelo real em branch local separada; não é validação geral de qualidade nem dependência de domínio. Não há benchmark comercial, clientes/testemunhos ou preços públicos validados nesta etapa.

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

Depois: classificação, casos/investigações, runner externo, piloto agêntico e DL por tarefa. Excluídos: treino distribuído, serving, GPU scheduler, registry completo, deploy automático e suporte simultâneo a todos os algoritmos.
