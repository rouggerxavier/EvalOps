# Leases de runner e terminalização

Fatia 3 do F4. O runner registrado pede trabalho, renova o lease e publica o desfecho. A API não executa código. `dispatch` e `dispatch_available` continuam false até a entrega do runtime de fixtures. Capabilities anunciam `runner_leases`/`leases_available`. Sem policy e budget habilitados não há plano, admissão nem lease.

## Protocolo

Toda chamada usa somente `X-EvalOps-Runner-Key`. A chave geral `X-EvalOps-Key` ou bearer humano recebe 401 nessas rotas e não há fallback.

1. `POST /v1/runners/{runner_id}/leases` com Idempotency-Key. Resposta `{"lease": null, "retry_after_s": 5}` quando não há trabalho (sem adquirir write locks de projeto/organização quando não há replay, fila ou lease vencido) ou `{"lease": {execution_id, attempt_id, lease_token, expires_at, lease_ttl_s: 60, heartbeat_interval_s: 20, manifest_hash, manifest}}`, com `Cache-Control: no-store`. O token aparece só nessa resposta e o banco guarda apenas o SHA-256. `expires_at` e `lease_ttl_s` respeitam `limits.wall_time_s` contado desde `claimed_at`. Repetir a mesma chave antes do primeiro heartbeat revalida a execução, reemite o token do mesmo lease e invalida o anterior. Depois do heartbeat ou se a revalidação falhar, a repetição recebe 409.
2. `POST /v1/executions/{id}/attempts/{attempt_id}/heartbeat` com `X-EvalOps-Lease-Token`. Renova a expiração para `min(agora + 60 s, claimed_at + limits.wall_time_s)` e devolve `cancel_requested`. O lease fica preso à credencial que o obteve.
3. `POST /v1/executions/{id}/attempts/{attempt_id}/complete` com `{status, exit_reason, capture_status, cost}`. O status é succeeded, failed, timed_out, cancelled ou uncertain. O custo segue `ReportedCost` (provided, unknown ou not_measured). Repetir o mesmo corpo devolve a mesma resposta. Um corpo diferente após o terminal recebe 409.

Uma execução tem um único attempt. Token inválido, attempt divergente, credencial revogada ou expirada, runner desabilitado e owner sem papel retornam todos o mesmo 401.

## Revalidação

Claim, heartbeat e complete revalidam a identidade original selada: chave e principal, ou JWT com versão, jti e expiração. Revalidam também membership, fontes transitivas, runner, policy corrente, budget da organização e reserva ativa. Policy mais permissiva não amplia o manifest selado.

A revalidação confronta também os valores e slots reservados com os limites vigentes. Overspend conhecido impede claim de outra execução ainda queued quando reserva + gasto ultrapassam o orçamento. Reduzir o orçamento do projeto ou o paralelismo de projeto/organização pode invalidar o replay de um lease já concedido: ele fecha como lost/uncertain, mantendo hold e slot. Gasto ocorrido em outra execução, sem mudança de policy/budget, não impede o runner de registrar o custo de um trabalho já running.

- Falha no claim inicial cancela a execução que não começou e libera a reserva com settlement conhecido zero.
- Falha no replay de claim, no heartbeat ou no complete deixa a execução uncertain. Se o complete autenticado pelo runner informar custo `provided`, o gasto informado é preservado e liquidado exatamente uma vez e o slot é liberado; se o custo for `unknown` ou `not_measured`, hold e slot permanecem retidos. O relatório recusado fica como evidência tardia.
- Um JWT humano dura 15 minutos por padrão e esse limite vale também para a execução que ele admitiu.

## Estados e dinheiro

- O complete aceito encerra o lease e grava o attempt. Custo provided liquida uma única vez pelo ledger existente. Overspend é preservado e gera o aviso `reported_cost_exceeds_reserved_limit`. Custo unknown mantém o hold e nunca vira zero. O relatório terminal é o ack de isolamento e libera o slot.
- Lease expirado (por TTL de 60 s ou por `limits.wall_time_s` desde `claimed_at`) sem terminal vira uncertain, com o hold e o slot mantidos. Nenhuma tentativa nova é criada: retry exige novo plano, admissão e reserva. A expiração é detectada de forma preguiçosa, sob lock de projeto, em claim, heartbeat, complete e cancel. Não há varredura em background.
- Desabilitar o runner ou revogar a credencial do lease deixa a execução uncertain na mesma transação.
- Cancel em running só registra o pedido. O runner confirma com complete `status=cancelled`. Esse status sem pedido recebe 422. Se o runner terminar com outro status antes do ack, esse desfecho prevalece.
- Um relatório após expiração, cancelamento ou terminal recebe 409 sem mudar o estado. Ele fica em `execution_late_reports`: deduplicado por hash, até 20 por attempt e sem liquidar custo.

Lock order: projeto, organização, identidade. Guards de banco tornam imutáveis o status terminal, os leases fechados, as colunas seladas e os relatórios tardios, e bloqueiam DELETE em `execution_ledger_entries`, `execution_leases` e `execution_late_reports`.

## SDK

```python
lease = runner.claim("RUNNER_ID", idempotency_key="claim-1")
runner.heartbeat(lease)        # a cada 20 s; pare se cancel_requested ou erro HTTP
runner.complete(lease, {"status": "succeeded", "exit_reason": "ok", "capture_status": "complete",
                        "cost": {"state": "provided", "amount_usd": "0.01", "measurement_source": "fixture"}})
```

## Migration e rollback

A migration 0021 é aditiva e cria `execution_leases` e `execution_late_reports`. O downgrade recusa tabelas com dados. Antes de reverter o código, desabilite a policy. Não apague leases nem evidência tardia, e não libere hold de gasto unknown para destravar o rollback.
