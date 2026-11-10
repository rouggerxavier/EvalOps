# Estado real e limites — 9 de novembro de 2026

## Escopo e método

Base auditada: `main` em `545149b`, igual à referência local `origin/main` no início. Inspeção de modelos, schemas, serviços, rotas, workers, páginas, SDK, testes, migrations e CI. PRs consultados via `gh pr list`; referências locais e worktrees consultadas sem checkout, merge ou fetch. Isso não garante que todas as branches remotas estejam atualizadas. A pasta `.agent/` já estava não rastreada; não é parte desta entrega.

Legenda: **V** = implementada e validada no escopo indicado; **P** = parcial; **D** = apenas documentação; **N** = proposta não implementada. Existência de testes não comprova produção. Resultados da verificação desta sessão estão em [revisão](../architecture/revisao-2026-11-09.md). Evidências históricas permanecem atribuídas aos commits originais.

## Inventário confrontado com implementação

| Capacidade | Estado | Evidência e limite |
|---|---|---|
| Organizações, projetos, memberships | V | `apps/api/app/models.py`, `deps.py`, `ownership.py`, testes `test_membership_permissions.py`. Papéis literais owner/member/viewer; permissões organizacionais, sem ACL individual por projeto para humanos. |
| Chaves por projeto/ambiente | V | `ApiKey`, `authenticate_api_key`, expiração/revogação, scopes `ingest,read,evaluate`; `evaluate` não é default. Não cobrem todas as operações. |
| Traces, spans, eventos | V | `Trace`, `Span`, `Event`; ingestão/SDK e `test_phase2_tracing.py`. `Span` tem input/output genéricos, mas mensagens/provider/model/tokens são centrados em LLM. Trace não equivale a processo executável. |
| Conversas e RAG | P | Resolvedor agrupa traces, serviço RAG consolida evidência declarada; não reconstrói memória nem comprova factualidade geral. |
| Rubricas versionadas | V | `RubricVersion`, parser YAML, registry com regex, keyword, length, JSON schema, exact match, cosine e judge. Campos ignorados são sinalizados; YAML descritivo não implica execução. |
| Avaliação por trace | V | `EvaluationRun.trace_id` e `rubric_id` obrigatórios; `EvaluationScore.score` 0–1 e `passed` não nulos. `eval_service.py` preserva erro/partial_failure; não suporta naturalmente RMSE ou matriz. |
| Datasets e referência esperada | P | `DatasetItem.input`, `expected_output`, metadata; criação manual e build-from-traces. Sem snapshot imutável/versionamento dedicado. Cópia de resposta observada não vira automaticamente verdade de referência. |
| Experimentos e histórico | P | `Experiment` fixa dataset/rubrica, variantes JSON; `ExperimentRun` persiste agregados. `experiment_service._synthesize_variant_output` concatena template e tags de modelo/parâmetros; **não chama modelo candidato**. Judge pode gerar custo real. |
| Comparação atual | P | Compara traces e variantes, com pass criteria e baseline. Sem inferência estatística nem pairing rigoroso por snapshot. Exceção de avaliador no experimento vira score zero: risco de falsa regressão. |
| Replay | P | `replay_worker._find_primary_llm_span` e `_call_provider`: uma chamada ao provider, mensagens reconstruídas. Não executa ferramentas, workflow, memória ou agente completo. Reserva/liquida custo e registra metadados de status. |
| Quality Gate | V | `quality_gate_service.py`, config persistida, pass/review/fail, janela/ambiente, métricas e denominadores. Regras específicas de traces/LLMs, grounding como proxy. Não é gate estatístico genérico de ML nem bloqueio de deploy por si só. |
| Feedback humano | V | `HumanFeedback` por trace, correção, tags, agregados; SDK envia por client_trace_id. Não é fluxo completo de aprovação de caso ou decisão de promoção. |
| SDK Python | V | tracer/uploader/client, retry, feedback e get_prompt; testes do SDK. Não tem cliente completo de experimentação, CLI operacional ou MCP nativo. |
| Workers e amostragem | V | arq/Redis: avaliação, replay, dispatch e amostragem; manutenção periódica. Amostragem fixa rubrica/versão e admite `uncertain`; fila não é sandbox de aplicações. |
| Orçamento, cotas, custo | P | planos/counters, budget de judge, reserva de replay. Não há ledger universal transacional por execução. Tokens/preços podem ser estimados; gasto desconhecido não pode ser anunciado como zero. |
| Privacidade e retenção | P | redaction opt-in limpa conteúdo; cleanup de tokens/exports e rotas de retenção. Não há DLP automática ou política completa de propagação a snapshots/artefatos futuros. Ocultar trace (`deleted_at`) não equivale a apagamento físico. |
| Auditoria | P | `AuditLog` identifica usuário; automação precisa principal de serviço e vínculo com chave. Não presumir cobertura de todos os efeitos. |
| ML clássico, métricas tipadas, registry | N | Nenhum núcleo específico no schema/registry atual. Strings provider/model não são registro de versões de modelos. |
| DL, curvas, GPU, visão/áudio | N | Propostas; não confundir spans genéricos com avaliação dessas tarefas. |
| Retomada de investigação entre agentes | N | Metadata e histórico existem; falta contrato persistente com hipóteses, evidências e decisão humana. |
| Promessas de replay integral/experimento real | D | Qualquer leitura nesse sentido das telas/docs excede a implementação acima. |

## Interface efetiva

Páginas em `apps/web/app/o/[org]/p/[project]`: overview, traces/lista/detalhe/compare, evaluations, experiments, prompts, rubrics, datasets, keys, exports e settings. Conta, login e registro fora do projeto. Server Components/Actions consomem API; preservar essa separação.

Datasets renderizam `input.messages` e `expected_output.assistant_message`: não servem como editor tabular de regressão. Experimentos exibem aviso `synthetic`, histórico e métricas por variante. Avaliações permitem rubricas; traces exibem ingestão, custo, evidências e feedback. Não há páginas de modelos, resíduos, matriz de confusão, investigação ou aprovação de promoção. Não redesenhar shell: [DESIGN.md](../../DESIGN.md) conserva tokens e layout. Há limites documentais antigos em DESIGN que já mudaram (por exemplo filtro de ambiente em atenção); este documento não altera a fonte visual.

## Histórico e branches

PR #44, autorização por papéis, integrado em `545149b`; #43, ocultação/origem dos experimentos, integrado; #42, troca de senha, integrado; #41, documentação Grankasa sintética, integrado. PR #45, recuperação por email, estava aberto na consulta; não é capacidade validada da main. Convites e retention locks também possuem branches locais: sua existência não implica entrega.

`codex/grankasa-uso-real` possui commit exclusivo `62a2804`. Diff contra merge-base: API build-from-traces, painel de casos, ações, testes e relatório. Sem merge desse commit na base auditada. Não promover automaticamente o patch: revisar compatibilidade com main e proveniência das referências esperadas.

## Grankasa: evidência disponível

Na main: `docs/integrations/grankasa.md` e `docs/audits/grankasa-qa-2026-11-09.json` registram harness scripted, duas baterias de 12 traces, sem provider real ou WhatsApp. Registro histórico de execução, não reexecução independente nesta sessão. O harness reside no repositório consumidor, não no núcleo do EvalOps.

Na branch `codex/grankasa-uso-real:docs/audits/grankasa-uso-real-2026-11-09.json`: 18 turnos/53 chamadas + caso salvo de 1 turno/2 chamadas; gasto declarado `0.006290115` USD. Confere aritmeticamente com contexto relatado (19/55/~0,00629). Registra catálogo sintético, modelo real, quatro falsos negativos iniciais e reavaliação após revisão de rubrica. **Nenhuma comparação live entre implementações alteradas foi executada**; comparador apenas testado offline. Os números são relato preservado, sem revalidação financeira ou do provider.

Necessidades transferíveis: capturar falha, revisar referência, selar fixtures, executar adaptador externo, comparar baterias pareadas e abrir evidência na web. Nenhuma entidade imobiliária entra no schema central.

## Testes, migrations e CI

Alembic chega a `0013_user_credential_version`; `0010_merge_quality_gate_cli` reúne heads anteriores. Não alocar número de migration nesta documentação: conferir head novamente antes de implementar. CI `ci.yml`: API pytest, SDK Python 3.9–3.12, web testes/build e upgrade PostgreSQL 16; runners `mac-ci` e Linux para migration. E2E Playwright existe, mas não aparece como job desse workflow. Testes API usam SQLite temporário e fila fake em conftest; passar pytest não prova concorrência PostgreSQL/Redis real.

## Dívidas que condicionam evolução

1. Não transportar o score normalizado para erros numéricos de ML.
2. Não liberar experimento sintético como evidência de mudança de modelo.
3. Fixar snapshot e avaliador antes de comparar; hoje dataset é mutável.
4. Propagar ownership para cada referência e artefato, inclusive via worker.
5. Separar falha técnica, erro do modelo, falta de rótulo e discordância do juiz.
6. API keys já executam batch de avaliação; ampliar essa infraestrutura em vez de inventar autenticação paralela.
