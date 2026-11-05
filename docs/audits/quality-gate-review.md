# Revisão integrada — Quality Gate

## Achados
Nenhum bloqueador de código pendente na revisão local final. A CI usa agora o runner self-hosted `mac-evalops` neste Mac, com label `mac-ci`. O resultado da HEAD deve ser conferido nos checks da PR. Dois achados foram corrigidos:

| Severidade | Área | Achado | Correção/evidência |
| --- | --- | --- | --- |
| Medium | Evidência | Uma avaliação sem scores individuais poderia aprovar qualidade | Exigir scores; teste `test_missing_individual_scores_cannot_approve_quality` |
| Medium | Configuração | Defaults não salvos poderiam reprovar o projeto | Limites sugeridos geram review até salvar; teste `test_unconfigured_limits_are_suggestions_and_never_fail_or_pass` |

## Escopo
- Branch `feat/project-quality-gate`, base `1141b80a`; data 2026-09-30.
- Model/config, migration, GET/PUT/status, serviços compartilhados, overview e Settings,
  landing/copy, testes, docs e CI.

## Veredito
Apto para revisão em PR de rascunho. Não é declaração de rollout em produção.
Contratos atuais preservados; feature aditiva; decisões e limites em `docs/quality-gate.md`.

## Verificação
- 381 testes API: incluindo 43 do gate, ownership, persistência, critérios,
  missing/partial evidence, erro de avaliador e upgrade/downgrade/reupgrade.
- 26 testes SDK em Python 3.12.
- 154 testes web, incluindo 9 comportamentais que executam TS/TSX de produção.
- Typecheck e build Next.js.
- E2E Chromium: Settings → save/reload → ingestão → avaliação real → aprovado →
  alteração de threshold → reprovado. Verifica review inicial e rotas tracing,
  evaluations, experiments; cinco métricas acessíveis por scroll em viewport 390px.
- Imagens de overview aprovado/reprovado, Settings e mobile foram inspecionadas.
- `git diff --check` sem erros. `origin/main` conferida em `1141b80a`.

## Riscos residuais
- PostgreSQL/volume de produção não testados; validar antes de rollout.
- Proxy de grounding, custo conforme já registrado e flags que dependem do juiz
  registrar `flags` têm limites explícitos; o gate não cria avaliações/segurança por inferência.
- E2E rodou em SQLite isolado e API com lifecycle de Redis desativado. Replay/Redis
  continuam cobertos pelos testes existentes, com mocks de fila.
- GitHub hosted não iniciou por orçamento no [run 36700206771](https://github.com/rouggerxavier/EvalOps/actions/runs/36700206771). A CI foi migrada para `mac-ci`, com venv por job, mesma matriz SDK e testes/build web. Operação em `docs/runbooks/ci-runner-self-hosted.md`; confirmar checks verdes na HEAD antes de merge.
- Há avisos de depreciação das dependências nos testes backend; suites passaram.

## Próximos passos
- Review e CI da HEAD antes de merge. Staging PostgreSQL antes de implantação.


## Retomada após integração com main — 5 de novembro de 2026

As evidências desta seção substituem as contagens e lacunas da revisão original
para a árvore executável `bf49569`; as seções acima preservam o registro anterior.

A [CI completa](https://github.com/rouggerxavier/EvalOps/actions/runs/41983179512)
passou nos sete jobs: 455 testes API, 165 web e build, 36 SDK em cada Python
3.9–3.12 e migração PostgreSQL. O typecheck local também passou.

Em PostgreSQL 16 dedicado, passaram os 117 testes de Quality Gate e regressões
P0/P1/produto. Os testes foram executados de seus caminhos originais, com um
adaptador temporário de engine/session no processo de pytest. O conftest padrão
continua isolando a suíte em SQLite; definir apenas DATABASE_URL não testa o
runtime PostgreSQL. A migração também passou por downgrade e novo upgrade,
preservando o projeto; o FK ON DELETE CASCADE foi verificado separadamente.

O E2E Chromium do gate passou com API e web locais, PostgreSQL 16 e Redis reais.
Cobre save/reload, ingestão, avaliação determinística, review/pass/fail e mobile.
Replay e chamadas a provedores externos não foram executados nesse E2E.

A revisão focal do merge conferiu regras automáticas compartilhadas, exclusão
de scores com erro, flags críticas, escopo por projeto/janela/ambiente e rollback.
Não foram encontrados novos bloqueadores nesse escopo. A implementação paralela
do juiz CLI permanece em worktree separado e não foi alterada nem integrada.
Suas migrações e os dois heads Alembic devem ser conciliados na integração futura.
Benchmark com volume de produção e validação em staging continuam pendentes.
