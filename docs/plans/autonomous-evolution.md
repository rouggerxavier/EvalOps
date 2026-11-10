# Evolução autônoma por fases

Modo standard. As SPECs continuam normativas; as fases abaixo representam implementação e evidência, não uma reclassificação automática das propostas.

| Fase | Estado | Próxima prova |
| --- | --- | --- |
| F0/F1 | Integradas em main pelo PR #47, merge 124aa18; CI do head verde | CI pós-merge 42888728647 verde; preservar gates existentes |
| F2 | Integrada em main pelo PR #48, merge 9b25492; CI head verde | Investigações retomáveis com revisões/If-Match, casos revisados por humano, proveniência synthetic/replay e revisão do patch Grankasa local |
| F3 | Integrada em main pelo PR #49, merge f852dfe; CI head verde | Classificação tipada, validade explícita, métricas e matriz/curvas na mesma API/SDK/web |
| F4 | Importador implementado; runner controlado pendente | Harness importado primeiro; runner externo somente com ledger/leases/política e testes locais de interrupção/egress |
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

## Evidência F3 (2026-11-10)

Classificação offline segue SPEC-003, com label_set ordenado, classe positiva binária, probabilidades opcionais, confusão/support, precision/recall/F1 class/macro/micro/weighted, ROC-AUC/AP binário e OvR, Brier/ECE/reliability binários. Referências rejeitadas e divisores zero são explícitos; ausência não vira zero. Correctness por amostra é persistida e reutilizada na descoberta de falhas. Comparação selada de tolerâncias permanece limitada à regressão; tentativa com classificação retorna 422.

API completa: 786 passaram/18 skips; fechamento dirigido de domínio e migration/concorrência SQLite/PostgreSQL: 16 passaram, incluindo dois testes adicionais de multiclasses e referência rejeitada; SDK: 85 passaram; web: 256; typecheck/build; E2E classificação + regressão, 375/1280 px: quatro passaram. Validação de valor externo ainda pendente.

Benchmark HTTP local (macOS, Python 3.12, SQLite dedicado, cinco execuções, classificação binária com 10 mil linhas e probabilidades): mediana 0.421s, p95 amostral 0.430s. Inclui autorização, lineage, cálculo, hashes e persistência; exclui setup e GET de métricas. Não é SLA produtivo nem medição de todos os limites combinados. Reproduzir com `scripts/benchmark_offline.py --task classification --api-url http://127.0.0.1:PORT/v1 --runs 5` em API descartável.

[Contrato e operação F3](../ops/offline-classification.md). Nenhuma migration adicional: contratos de conteúdo versionados sobre tabelas existentes.

F2 CI pós-merge 42895689264 verde. F3 E2E final de classificação após correctness: dois passaram.

## Primeira entrega F4 — importação de harness

Execution/ExecutionAttempt importados e imutáveis, manifests/hash, vínculos com snapshots/modelos/predições/traces, desfechos declarados, custo Decimal provided/unknown/not_measured sem zero implícito. API/SDK/CLI/web compartilham a captura e explicitam proveniência parcial; sem dispatch, orçamento reservado ou execução no processo API. Investigação aceita execution:ID. Contrato e rollback em [operação](../ops/external-harness-imports.md).

Review encontrou divergência entre ambiente explícito e ambiente da chave na criação de snapshot sobre fonte compartilhada. Teste RED retornou 201 em destino incompatível; correção no load comum exige 404 e impede publicação por outras operações. Autorizações diretas de manifest também verificam o ambiente da chave.

Gates dirigidos: 101 testes de autorização/contrato passaram; fechamento de importador e ambiente: 30 passaram; migration e concorrência PostgreSQL: seis passaram; E2E captura 375/1280 px: dois passaram. API completa: 798 passaram/19 skips; SDK: 87 passaram; web: 256; typecheck/build passaram. Fechamento de contratos estritos: 12 passaram. Nenhuma chamada externa paga, alteração de worktree Grankasa ou tráfego produtivo.

### Próxima fatia F4

Implementar controles antes de dispatch: policy versionada por projeto; registro/credencial de runner com escopo restrito; planos selados e reserva atômica Decimal; lease único/heartbeat; estado incerto após perda de worker iniciado; cancelamento só após ack; publicação terminal tardia vira evidência sem sobrescrever estado; retry incerto exige autorização/orçamento novos. Revalidar chave original, membership e fontes em início/publicação. Reusar padrões de reserva do replay sem duplicar UsageCounter. Provar corridas em PostgreSQL dedicado e Redis isolado; harness de dois turnos/tools fake com egress negado. Runner externo não é sandbox gerenciado.

F3 CI pós-merge 42897661392 verde. F4 seed limitado a int64 e dirty boolean estrito; JSON inválido é recusado antes de publicar.
