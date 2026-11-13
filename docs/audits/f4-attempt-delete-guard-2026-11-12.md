# F4: preservação de attempts após integração paralela

## Achado e escopo

A main `b9bc2a2` preservava leases, relatórios tardios e ledger contra DELETE,
mas permitia apagar `execution_attempts`. A branch local `feat/f4-leases`
`4bc133b` já continha essa proteção; ela ficou fora da implementação integrada.
A reprodução isolada confirmou um attempt apagado na main e DELETE recusado
na branch local. As worktrees anteriores foram preservadas.

Esta correção acrescenta somente o guard de DELETE, sem modificar as regras de
tempo máximo, revalidação, custos, slots ou polling da main. Base remota:
`b9bc2a2cc97c6c5faa205b3d13db3e6659c367d6`; árvore inicial local equivalente:
`8d983ab8b9beb777cd9c6402e76de4d071cc256f`.

## Implementação e rollback

- ORM: trigger `immutable_execution_attempts_delete` em SQLite e PostgreSQL.
- Alembic: nova revisão `0023_attempt_delete_guard`, após
  `0022_organization_invitations`. Migrations publicadas permanecem intactas.
- Upgrade acrescenta o trigger sem transformar registros.
- Downgrade para `0022_organization_invitations` remove somente esse guard;
  dados e proteção contra UPDATE permanecem, mas DELETE direto volta a ser permitido.
- O teste de convites verifica sua versão específica antes de subir até a head
  atual para executar `alembic check` em PostgreSQL.

## Verificação

O teste existente de terminalização foi ampliado para tentar apagar o attempt.
Antes da correção: **1 failed**, pois o DELETE não lançava erro. Depois:

```text
python -m pytest -q tests/test_runner_leases.py tests/test_runner_lease_budgets.py tests/test_runner_leases_postgres.py tests/test_invitation_migration.py tests/test_task_migration.py tests/test_execution_imports.py
46 passed, 14 skipped
```

Os skips exigem PostgreSQL dedicado. O CI existente executa o mesmo arquivo de
leases com PostgreSQL16, incluindo bloqueio via ORM e round-trip
`0022 -> 0023 -> 0022 -> 0023` com attempts, leases e relatórios existentes.
O teste compara os registros antes e depois, verifica que o downgrade remove
somente o novo guard, e que o re-upgrade restaura o bloqueio.

## Decisão de integração

Modo standard; perfil de CI full pelo impacto de migration. Self-review do diff
e regressões locais concluídos; nenhum segredo, arquivo de ambiente ou alteração
de outra unidade incluído. Publicação em branch própria, com um único head.

MERGE BLOCKER: CI do SHA publicado, incluindo PostgreSQL, deve passar.

NEXT-WORK BLOCKER: nenhum; leitura e preparação de D3 podem continuar. A branch
antiga de D3 exige composição com a main e cobertura de leases/relatórios.

POST-MERGE OBSERVATION: observar o CI da main; falha posterior exige investigação.

Aplicação em produção e exclusão destrutiva não fazem parte desta correção.
