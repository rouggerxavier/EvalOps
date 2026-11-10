# Evolução autônoma por fases

Modo standard. As SPECs continuam normativas; as fases abaixo representam implementação e evidência, não uma reclassificação automática das propostas.

| Fase | Estado | Próxima prova |
| --- | --- | --- |
| F0/F1 | Integradas em main pelo PR #47, merge 124aa18; CI do head verde | CI pós-merge 42888728647 verde; preservar gates existentes |
| F2 | Implementada; gates locais em fechamento | Investigações retomáveis com revisões/If-Match, casos revisados por humano, proveniência synthetic/replay e revisão do patch Grankasa local |
| F3 | A seguir, independente após F1 | Classificação tipada, validade explícita, métricas e matriz/curvas na mesma API/SDK/web |
| F4 | Depende de F2 e SPEC-009 | Harness importado primeiro; runner externo somente com ledger/leases/política e testes locais de interrupção/egress |
| F5 | Depende de F3 e piloto escolhido | Curvas/recursos/artefatos importados; não escolher domínio de piloto sem evidência |
| F6 | Condicional, sob demanda | Experimento de valor medido antes de cada expansão; não fabricar resultados de pilotos |

## Fatias F2

1. Investigation/Revision, labels cumulativos, recibos e histórico imutável; API/SDK/CLI compartilham estado. Escrita concorrente rejeita If-Match antigo sem perder histórico.
2. Curadoria textual e numérica sobre DatasetItem; classificação humana inicial de legado, referência draft por padrão, revisão humana auditada e fontes transientes revalidadas.
3. Interface de investigações/casos, continuidade pelo mesmo ID e evidências de falhas; distinguir erros técnicos de qualidade e synthetic de execução real.
4. Revisão somente em leitura da branch Grankasa existente, preservando mudanças locais. Nenhuma mensagem, chamada de modelo paga ou tráfego produtivo é autorizado por essa revisão.

Read first: SPEC-004/007/008/009, modelos, serviço de tarefas, rotas e testes de F0/F1, cliente SDK, ações web e DESIGN.md. Reusar o domínio e os componentes existentes.

Gates: testes de domínio/API e matriz de rotas; SDK/CLI; migration SQLite/PostgreSQL preservando legado; concorrência real; web tests/typecheck/build; E2E 375/1280 px. CI bloqueia merge. Gates pesados locais rodam em sequência. Rollback mantém dados e revisões; downgrade com evidências é recusado.

Sem bloqueio local atual. Validação de valor por engenheiros/pilotos é evidência externa pendente; nenhuma simulação será apresentada como participação humana real.

## Evidência F2 (2026-11-10)

API: 776 testes passaram, 18 skips de gates opcionais/legados. Gates PostgreSQL dedicados: migration round-trip e preservação de legado passaram em SQLite/PostgreSQL; três testes PostgreSQL passaram, incluindo dois escritores simultâneos, uma revisão aceita e outra recusada com 409. SDK: 83 testes passaram. E2E Chromium em 375/1280 px: captura de trace fixture, classificação de origem, rascunho sem resposta esperada copiada, revisão humana com motivo, investigação retomada pelo mesmo ID e conflito antigo recusado.

Patch local Grankasa revisado somente em leitura: worktree `EvalOps-grankasa-uso-real`, branch `codex/grankasa-uso-real`, commit `62a28048e351dc92f983b088f3a68da65af084ce`. Reaproveitado o resolver de saída já existente no domínio. A cópia automática de saída para referência esperada foi substituída por `observed_output`, `expected_output=null` e estado draft. Nenhum cherry-pick nem alteração naquele worktree; nenhum piloto externo foi repetido.

Rollback F2: reverter código mantém evidências no banco; downgrade 0015 recusa investigações ou recibos de revisão existentes. Não apagar histórico para liberar downgrade.

Web: 256 testes passaram, typecheck e build passaram. Review integrada conferiu autorização transitiva humana/serviço, recibos, conflitos e isolamento. [Operação e contratos](../ops/investigations-curation.md).
