# CI Throughput Decision — Quality Gate

## Contexto
- Mudança: backend/API/contratos/migration, frontend, documentação e E2E focal.
- Modo: standard. Runner: self-hosted `mac-ci`, neste Mac, registro próprio do EvalOps.
- Próxima unidade: nenhuma; objetivo é uma PR de rascunho revisável.

## Decisão
```yaml
selected_mode: standard
ci_profile: full
ci_blocking_point: before_merge
ci_wait_policy: background
publication_hold: true
next_work_policy: continue_independent
e2e_tier: focal
```

## Bloqueios
- MERGE BLOCKER: CI da HEAD deve estar verde antes de integrar. A CI de `bf49569` concluiu os sete jobs com sucesso após restaurar `mac-evalops`. Commits seguintes devem conferir seus próprios checks.
- NEXT-WORK BLOCKER: none — revisão e documentação podem continuar.
- POST-MERGE OBSERVATION: not_applicable — merge/deploy não fazem parte desta entrega.
- Publication hold impede declarar readiness de produção/deploy com migração sem validação no ambiente alvo. A PR de rascunho contém trabalho para revisão.

## Gates
- Local: suíte completa API (incluindo ownership e upgrade/downgrade), SDK em
  Python 3.12, testes web, tipos/build e E2E real review/pass/fail desktop/mobile.
- Remoto: workflow `ci`, testes API; SDK Python 3.9–3.12; testes web e build.
- PostgreSQL 16: migração, rollback, novo upgrade e cascade verificados localmente;
  `migrate-postgres` passou na CI da HEAD `bf49569`.
- Adiados: validação com dados e volume reais → staging antes de rollout.
- Runner policy: máquina compartilhada com fluxo-nexo e outros runners; evitar
  cargas locais pesadas durante CI. Jobs do EvalOps executam sequencialmente.
- Concurrency: cancela runs superadas da mesma PR; push apenas em `main` evita
  duplicação push/PR. A HEAD atual é a referência de validação.
- Auditoria após verde: incremental, com alvo nos contratos e migração.


## Evidência de retomada — 5 de novembro de 2026

- [CI da HEAD executável `bf49569`](https://github.com/rouggerxavier/EvalOps/actions/runs/41983179512):
  sete jobs verdes; API 455, web 165 e build, SDK 36 por versão Python 3.9–3.12,
  além da migração PostgreSQL.
- Typecheck local: `cd apps/web && npx --no-install tsc --noEmit` passou.
- PostgreSQL 16 local: 117 testes de gate e regressões P0/P1/produto passaram.
  Um adaptador temporário substituiu somente engine/session do `conftest` no
  processo de testes. Os arquivos permaneceram no repositório; não houve as três
  falhas de caminhos relativos do ensaio anterior. A fixture padrão do projeto
  continua usando SQLite, mesmo quando `DATABASE_URL` aponta para PostgreSQL.
- E2E Chromium do gate passou com API, migrações, PostgreSQL 16 e Redis reais;
  formulário, persistência, review/pass/fail, viewport mobile e navegação aos
  módulos anteriores. O teste não executa replay nem chama um juiz LLM externo.
- PostgreSQL: upgrade/downgrade/reupgrade preservou o projeto; remover o projeto
  removeu sua configuração por `ON DELETE CASCADE`.
- Runner dedicado 2.338.2 restaurado e online. Serviço e `caffeinate -i`
  persistentes no LaunchAgent. Nenhum runner de outro repositório foi alterado.
