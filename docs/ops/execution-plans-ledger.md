# Planos selados e admissão de execução

Esta entrega F4 prepara planos, reserva orçamento e permite cancelar antes do lease. Não inicia processos. Capabilities anunciam plan_sealing/budget_admission, mas dispatch continua false até entrega de leases e runtime.

## Autoridade e orçamento

Owner configura budget da organização em `GET/PUT /v1/projects/{project_id}/organization-execution-budget`. O valor é compartilhado entre projetos da organização. PUT exige If-Match; versão 0 significa ausência/configuração desabilitada. Cada alteração cria revisão imutável. Redução abaixo de reserva + gasto conhecido do período é recusada. Desabilitar impede admissões novas sem apagar reservas.

Policy do projeto continua owner-only e versionada. Inclui max_cost_per_run_usd, monthly_budget_usd, max_parallel, max_wall_time_s (default 300), max_tool_calls (20) e max_tokens (10000), ambientes/adapters e fixtures_only. Runner declara capacidade max_parallel (default 1). Recibos de policy/registro da versão anterior continuam válidos quando novos campos não são enviados.

Novo plano exige read+write; admissão exige read+write+evaluate, pois a execução futura produzirá predições. Avaliar predições já importadas continua exigindo read+evaluate. Credencial de runner não recebe esses scopes gerais.

## API, SDK, CLI e web

1. POST `/v1/projects/{p}/execution-plans` com `{runner_id,manifest}` e Idempotency-Key. Manifest segue contrato do importador, mas modos dispatcháveis são local_model/application_adapter/agent_behavioral. Replay LLM continua na superfície legada; offline_predictions não precisa de runner. Modo agêntico exige fixtures declaradas. Servidor valida fontes, ambiente, snapshot hash, runner e policy, limites e budget habilitado.
2. GET `/v1/execution-plans/{id}` consulta manifest/hash, runner e revisões seladas. GET de lista em `/v1/projects/{p}/execution-plans` tem paginação autorizada. Criar plano não reserva nem executa.
3. POST `/v1/projects/{p}/executions` com `{plan_id}` e Idempotency-Key retorna 202/queued. Policy/budget devem continuar nas versões seladas no momento da admissão. Reserva é atômica por organização/projeto, antes da fila. Mesma operação não duplica hold; quota excedida retorna 402 e paralelismo 429, sem linhas parciais.
4. GET `/v1/executions/{id}/budget` mostra teto, hold, gasto conhecido/ausente, slots e ledger. Não inferir gasto zero de ausência. Importações externas não possuem essa reserva.
5. POST `/v1/executions/{id}/cancel` é idempotente. Em queued, prova ausência de lease e libera hold/slot com settlement conhecido zero. Em running, apenas solicita cancelamento; terminalização depende de ack na entrega seguinte. Owner pode parar trabalho oculto sem receber manifest/fontes; principal continua sujeito às fontes. Execução importada não é cancelável por esse controle.

SDK: `create_execution_plan`, `get_execution_plan`, `enqueue_execution`, `execution_budget`, `cancel_execution`. Web: Avaliações > Execuções e evidências, preparar plano por arquivo/editor JSON, conferir manifest, reservar/enfileirar e cancelar. Owner configura budget organizacional na página de runners.

```bash
evalops execution-plan-create --project PROJECT --file plan.json --idempotency-key SEAL --json
evalops execution-plan PLAN_ID --json
evalops execution-start --project PROJECT --plan PLAN_ID --idempotency-key ADMISSION --json
evalops execution EXECUTION_ID --json
evalops execution-cancel EXECUTION_ID --json
```

execution-start significa admissão/queued, não confirmação de que código iniciou. API/SDK/web consultam o mesmo registro e ledger.

## Contabilidade e incerteza

USD tem oito casas. Ledger append-only guarda Decimal; contas de quota usam unidades inteiras de 10^-8 USD, inclusive no SQLite. Limite v1 de 1 bilhão USD evita overflow. Não há cálculo monetário em float nem conversão cambial. Reserva registra limite autorizado; settlement registra custo reportado com fonte/versão. Ledger não é invoice verificada de provider.

Contas usam período da reserva. Settlement posterior continua nesse período. Slots ativos são somados em todos os períodos; mudar mês não reinicia paralelismo de execução incerta. max_parallel limita slots admitidos, incluindo queued e incerteza sem isolamento; paralelismo interno pesa na reserva.

Gasto unknown mantém hold e slots. Overspend conhecido fica registrado e impede próxima admissão pelo saldo; não truncar valor real reportado. Testes de settlement usam fixtures de custo, não chamadas pagas. Conciliação pública/leases ainda não estão disponíveis nesta entrega; não liberar hold incerto manualmente para habilitar retry.

Identidade original é selada por IDs, scopes, jti/expiry ou key ID e credential_version, sem guardar segredo. Worker futuro revalidará tudo em cada fronteira. Revogação não concede retry nem remove evidência; outro ator autorizado pode consultar/cancelar conforme papel e fontes.

## Migração e evidência

Migration 0018 é aditiva para budget/planos/ledger e amplia estados de Execution. Capturas existentes recebem origin=external_import; conteúdo/hash/status terminal permanecem intactos e imutáveis. Guards bloqueiam UPDATE e DELETE do ledger. Downgrade recusa planos, reservas, contas ou execuções controladas. Antes de rollback de código, desabilite admissão e cancele queued na versão compatível. Preserve banco e reservas incertas; código anterior não deve interpretar execuções controladas como capturas importadas. Restaure versão compatível para conciliação.

Gates verificam frações de USD, concorrência entre projetos da mesma organização, hold unknown/paralelismo entre períodos, overspend, permissões/IDOR, recibos antigos e revogação original. Round-trip SQLite/PostgreSQL preserva capturas anteriores e seus guards. E2E 375/1280 px confere reserva/cancelamento contra API; nenhum processo externo ou chamada paga participa desses testes.
