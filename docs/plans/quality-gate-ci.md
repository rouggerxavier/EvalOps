# CI Throughput Decision — Quality Gate

## Contexto
- Mudança: backend/API/contratos/migration, frontend, documentação e E2E focal.
- Modo: standard. Runner remoto: hosted (`ubuntu-latest`).
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
- MERGE BLOCKER: CI da HEAD deve estar verde antes de integrar. Jobs remotos não iniciaram por orçamento do GitHub Actions; liberar orçamento e repetir CI.
- NEXT-WORK BLOCKER: none — revisão e documentação podem continuar.
- POST-MERGE OBSERVATION: not_applicable — merge/deploy não fazem parte desta entrega.
- Publication hold impede declarar readiness de produção/deploy com migração sem validação no ambiente alvo. A PR de rascunho contém trabalho para revisão.

## Gates
- Local: suíte completa API (incluindo ownership e upgrade/downgrade), SDK em
  Python 3.12, testes web, tipos/build e E2E real review/pass/fail desktop/mobile.
- Remoto: workflow `ci`, testes API; SDK Python 3.9–3.12; testes web e build.
- Adiados: PostgreSQL e benchmark de volume → ambiente de staging antes de rollout.
- Runner policy: nenhuma contenção com runner hosted; cargas locais independentes.
- Concurrency: workflow atual não cancela runs superadas; nenhuma política global
  alterada nesta entrega. A HEAD atual é a referência de validação.
- Auditoria após verde: incremental, com alvo nos contratos e migração.
