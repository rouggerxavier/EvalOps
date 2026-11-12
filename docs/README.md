# Documentação EvalOps Studio

Estado atual e proposta futura são separados. Auditorias históricas permanecem datadas; não constituem contrato atual sem confronto com código. A reorganização de 2026-05-21 faz parte do histórico, não autoriza apagar registros desta rodada.

## Estratégia e evolução proposta — 2026-11-09

- [Produto](../PRODUCT.md): posição, públicos, princípios e limites atuais/futuros.
- [Auditoria do estado real](audits/estado-real-2026-11-09.md): base `545149b`, capacidades, branches e Grankasa.
- [Arquitetura e decisões](architecture/evolucao.md): opções, reuso, consequências e questões abertas.
- [Referências oficiais](architecture/referencias-2026-11-09.md): mercado, complementaridade e hipóteses.
- [SPEC-001 a SPEC-009](specs/README.md): contratos propostos e dependências.
- [Roadmap e primeira vertical](plans/roadmap-evolucao.md): regressão offline web/API, critérios e pacotes delegáveis.
- [Revisão e relatório da rodada](architecture/revisao-2026-11-09.md): verificação, riscos e limites.
- [Sistema visual atual](../DESIGN.md): preservado; evolução humana em SPEC-008.

## Implementação e operação existentes

- [Quality Gate: contrato e demo](quality-gate.md).
- [Migrations](ops/database-migrations.md), [amostragem](ops/avaliacao-amostragem.md), [conta/senha](ops/conta-senha.md).
- [Autorização por membership](security/r1-membership-permissions.md).
- [Integração sintética Grankasa](integrations/grankasa.md).
- [Ocultação de traces](ocultar-trace-2026-11-09.md).
- [SDK Python](../packages/sdk-python/README.md).
- [CI self-hosted](runbooks/ci-runner-self-hosted.md).

## Registros históricos preservados

- [Plano Quality Gate](plans/quality-gate.md), [CI do gate](plans/quality-gate-ci.md), [revisão](audits/quality-gate-review.md).
- [Auditoria de código 2026-11-05](audits/auditoria-codigo-2026-11-05.md), [produto](audits/auditoria-produto-2026-11-05.md).
- [Auditoria front/back](audits/front-back-product-audit-2026-05-21.md), [bugs de implementação](audits/front-back-product-implementation-review-bugs.md).
- [QA redesign](audits/redesign-qa-2026-11-08.md), [amostragem](audits/amostragem-qa-2026-11-08.md), [conta](audits/conta-senha-2026-11-09.md).
- [QA Grankasa sintética](audits/grankasa-qa-2026-11-09.json).
- [Planos anteriores de implementações](implementações.md).

## Regras documentais

Citar arquivos/rotas reais para capacidade atual; marcar proposta explicitamente. Preservar auditoria e proveniência; corrigir por adendo datado, sem apagar história. Relatório em branch não é entrega na main. Critério de aceite não é teste executado. Ao implementar, atualizar contrato, documentação e evidência no mesmo incremento.
