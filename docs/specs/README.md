# Especificações da evolução

Todas **propostas**, não funcionalidades entregues. Não há migrations ou código nesta rodada. [Auditoria](../audits/estado-real-2026-11-09.md), [decisões](../architecture/evolucao.md), [roadmap](../plans/roadmap-evolucao.md) e [revisão](../architecture/revisao-2026-11-09.md) delimitam execução.

| SPEC | Contrato | Dependências principais |
|---|---|---|
| [001](SPEC-001.md) | Visão e vocabulário | nenhuma |
| [002](SPEC-002.md) | Snapshots, modelos, predições, métricas | 001 + 009 mínima |
| [003](SPEC-003.md) | ML clássico, regressão primeiro | 002 |
| [004](SPEC-004.md) | API, SDK, CLI, MCP, investigação | 002 + 009; comparação usa 007 |
| [005](SPEC-005.md) | Runner externo e execução | 002/004/009 |
| [006](SPEC-006.md) | DL por tarefa e artefatos | 002/003; execução usa 005 |
| [007](SPEC-007.md) | Comparação, casos e decisão | 002/003/009 |
| [008](SPEC-008.md) | Web integrada | 002/003/004; amplia conforme 006/007 |
| [009](SPEC-009.md) | Segurança e operação transversal | 001; entrega por subsets |

Ordem não é numérica. A fundação de 009 não depende de implementar runner ou MCP. Interfaces estão sob `/v1`; caminhos dentro de 002 omitindo prefixo herdam `/v1`. Contratos novos não mudam envelopes legados sem migração explícita. Cada implementador deve reconferir main, schema e OpenAPI antes de editar.
