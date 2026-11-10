# Importação de harness externo

Primeira entrega F4. Importa evidências de execução ocorrida no ambiente do consumidor. Não inicia processo, não reserva orçamento e não autoriza efeitos externos. Descoberta informa `execution_capabilities.import=true`, `dispatch=false`, `managed_sandbox=false`.

## Fluxo

1. Importe dataset, snapshot imutável e versão de modelo. Importe predições pelas rotas offline existentes, incluindo o manifest do produtor.
2. Capture no harness o commit, dirty state/digest do patch, config digest, runtime, ambiente/dependências, estado inicial, fixtures, limites declarados, timestamps, desfecho e custo reportado. Não inclua credenciais ou conteúdo sensível nos digests/metadados públicos.
3. Envie `{manifest,result}` para `POST /v1/projects/{project_id}/execution-imports`, com `Idempotency-Key`. Manifest e resultado são contratos fechados no OpenAPI. Snapshot hash deve coincidir; predições devem pertencer ao mesmo snapshot/modelo/projeto/ambiente. Traces vinculados passam pela mesma autorização transitiva.
4. Consulte `GET /v1/executions/{id}` ou `/v1/projects/{project_id}/executions`. A web oferece Avaliações > Evidências de execução, upload/editor JSON e detalhe dos hashes selados. SDK: `import_execution`, `get_execution`, `list_executions`.
5. Avalie o prediction_set com o avaliador da tarefa. A captura não substitui métricas nem política de qualidade; `decision=null` da execução é diferente de `decision` de uma avaliação. Vincule `execution:ID` a uma investigação para registrar revisão e próximos passos.

CLI usa credenciais somente no ambiente:

```bash
evalops execution-import --project PROJECT --file capture.json --idempotency-key OPERATION --json
evalops execution EXECUTION_ID --json
```

## Contrato

Manifest v1 declara mode (`offline_predictions`, `local_model`, `application_adapter`, `llm_call_replay` ou `agent_behavioral`), environment, snapshot_id/hash, candidate, adapter, evaluator_versions, initial_state_digest, fixture_digests, seed/repetitions, limits e effects_policy=fixtures_only. Modos são alegações do produtor, não prova de que EvalOps executou um agente. Candidate exige application_ref/code_commit/code_dirty/config_digest/model_versions; dirty exige patch_digest. Adapter exige id/version/environment_digest/runtime; dependency_lock_digest e hardware opcionais deixam proveniência parcial.

Limits contém max_cost_usd (Decimal), wall_time_s, max_tool_calls, max_tokens e max_parallel. Limites importados não são aplicados retroativamente. Effects policy declara intenção; importador não contém nem audita o processo externo.

Result contém status terminal, exit_reason, started_at/ended_at com timezone, prediction_set_id, trace_ids, capture_status e cost. Sucesso exige predições; falha/uncertain podem preservar captura sem predições. Nenhuma execução uncertain gera retry ou chamada automática.

Cost.state é provided, unknown ou not_measured. Provided exige amount_usd e measurement_source; pricing_version opcional. Unknown/not_measured exigem amount_usd=null. Zero só pode existir como valor explicitamente reportado. USD é unidade fixa; não há conversão cambial. Overspend/duração acima do limite declarado geram warnings preservando evidência, sem apagar gasto ocorrido.

Servidor sela manifest_hash, result_hash e hashes das entradas efetivamente vinculadas. `producer=external_harness`, `provenance=partial` e avisos de captura externa não verificada permanecem explícitos, mesmo quando o produtor declara capture_status=complete. Hash prova integridade do conteúdo recebido, não autenticidade do ambiente externo. Dados brutos/custos externos continuam alegações do produtor.

## Segurança e rollback

Write exige read das fontes, escopo write e ambiente compatível da chave. Snapshot compartilhado não autoriza principal a criar destino de outro ambiente. A autorização comum recusa divergência entre ambiente explícito e ambiente da chave, inclusive na criação de snapshots. Recibos revalidam fontes e credenciais; restrição posterior oculta captura e investigação derivada.

Migration 0016 adiciona executions/execution_attempts e guards de imutabilidade SQLite/PostgreSQL. Downgrade exige tabelas vazias; rollback de código preserva evidências. Não apagar capturas para permitir downgrade.

Próxima entrega F4: política owner-only, runner registrado, ledger Decimal, planos selados, leases/heartbeat, cancelamento com ack, expiração após início incerto, recusa de publicação tardia e conciliação. Esses controles precisam de provas PostgreSQL/Redis e fixture de egress/interrupção antes de anunciar dispatch. Piloto real A/B com tools em fixtures continua pendente.
