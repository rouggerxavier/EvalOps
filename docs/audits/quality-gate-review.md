# Revisão integrada — Quality Gate

## Achados
Nenhum bloqueador pendente na revisão local final. Dois achados foram corrigidos:

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
- Proxy de grounding, custo conforme já registrado e ausência de flag executor
  têm limites explícitos; o gate não cria avaliações/segurança por inferência.
- E2E rodou em SQLite isolado e API com lifecycle de Redis desativado. Replay/Redis
  continuam cobertos pelos testes existentes, com mocks de fila.
- Há avisos de depreciação das dependências nos testes backend; suites passaram.

## Próximos passos
- Review e CI da HEAD antes de merge. Staging PostgreSQL antes de implantação.
