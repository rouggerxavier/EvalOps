# F4 — fechamento do protocolo de leases

Continuação do PR #52. Base de integração: main `7f841ee`. Reaproveita a fatia
de leases `9026e3a` e a correção revisada `424ae12`, composta com a main sem
reverter a coordenação por trace do PR #53.

## Escopo e revisão

- Lease único com token armazenado somente como hash; replay revalida grants.
- Claim e heartbeat limitados ao wall_time_s contado do claim inicial.
- Complete recusado com custo provided preserva gasto, liquida uma vez e libera
  slot; custo desconhecido nesse caminho mantém hold e slot.
- Guards de UPDATE/DELETE no ORM e Alembic preservam evidências.
- Polling realmente ocioso não adquire write locks; fila vazia não impede expiração.
- Revalidação confronta orçamento e concorrência agregados com limites vigentes.
- SDK mantém o retorno lease ou None; dispatch continua false, sem runtime novo.

Revisão integrada: sem bloqueador identificado nos caminhos inspecionados.
Foram conferidos rotas runner-only, matriz de permissões, token/credencial,
terminalização, settlement idempotente, rollback e composição com D2.

## Evidência executada

- API dirigida: **93 passed, 14 skipped**, cobrindo leases, budget, runner control,
  migrations SQLite, imports e coordenação/locks por trace. Os skips exigem PostgreSQL.
- As quatro regressões de orçamento/paralelismo falham com o código `9026e3a`
  pelos comportamentos incorretos: overspend ainda entrega queued e os três
  replays após redução de limites retornam 200. Nenhuma falha de setup no RED.
- Após restaurar a implementação final, os **6 testes** do novo arquivo passam.
  Incluem preservação de custo de trabalho já running e expiração persistida
  antes de recusar replay.
- SDK: **2 passed** nos testes runner-only/token/claim/heartbeat/complete.
- Whitespace e diff conferidos; sem alteração de dependências ou segredos.

Comando API, executado em apps/api com Python 3.12 e dependências existentes:

```bash
python -m pytest -q -p no:cacheprovider tests/test_runner_lease_budgets.py tests/test_runner_leases.py tests/test_runner_leases_postgres.py tests/test_runner_control.py tests/test_execution_budget.py tests/test_task_migration.py tests/test_execution_imports.py tests/test_trace_execution_coordination.py tests/test_trace_execution_lock.py
```

## CI e limites

Modo standard; perfil CI full por incluir schema/migration. A integração exige
os checks completos do SHA publicado. O job migrate-postgres executa a suíte
de leases, incluindo as mesmas quatro regressões em schema PostgreSQL descartável.
Suíte API completa, SDK nas quatro versões Python e build/testes web rodam no CI.

Docker e sockets locais estão indisponíveis neste executor; PostgreSQL e SDK
HTTP completo não foram revalidados aqui. Não atribuir os resultados de execuções
anteriores a esta validação. CI pendente bloqueia merge, sem autorizar skip silencioso.

Migration 0021 aponta para 0019 e tem head única nesta composição. Convites/0020
ainda não integra a main e não foi copiado para esta branch; sua futura integração
deverá compor explicitamente a cadeia. Downgrade de leases com evidência é recusado.

## Próxima fatia

O runtime externo de fixtures (fatia 4), a reconciliação pública de uncertain e
a varredura em background não fazem parte desta entrega. Nenhuma chamada paga,
ativação de produção, limpeza de evidência ou mudança no JWT foi realizada.
