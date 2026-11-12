# Backend Slice Plan — controle de runner externo

## Objective

Executar manifest selado em runner externo registrado, com autorização revalidada, reserva Decimal e lifecycle que preserve gasto/efeitos incertos.

## Out Of Scope

- Hosting gerenciado, execução no processo API, treino/serving, credenciais de produção, ferramentas com external_write e alegação de contenção de código hostil no host cliente.

## Locked Decisions

- Continuar em standard, sem delegação; CI full antes de merge e trabalho seguinte local enquanto CI roda.
- Importador F4 permanece somente evidência; não converter capturas importadas em leases nem autorizações de gasto.
- Policy owner-only e revisionada; ausência de policy deixa dispatch desabilitado.
- Runner tem credencial própria, armazenada como hash, sem scopes read/write/evaluate da API comum. Membership do owner responsável é revalidada.
- Manifest, policy version e credencial original são selados. Lease/publicação revalidam fontes e permissões, não apenas dados copiados.
- Gasto desconhecido mantém reserva; nenhuma repetição automática de tentativa iniciada incerta. Cancelamento exige ack ou isolamento encerrado.
- Ledger novo apenas para novas execuções controladas. Não duplicar cobrança do replay/UsageCounter.

## Open Questions

- Piloto externo A/B autorizado e valor medido dependem de consumidor real. Fixtures locais não substituem esse aceite.
- Não há dúvida bloqueante para fundamentos locais, protocolo de runner e testes sem chamadas pagas.

## Read First

- SPEC-005/009 e estados SPEC-001; contratos/importador F4, service/access/immutability, uso de TaskReceipt e auditoria.
- Workers replay/sampling, usage_service, autenticação de chaves, testes de membership/ambiente e concorrência PostgreSQL.
- SDK/CLI, padrões web e DESIGN.md antes de alterar as superfícies correspondentes.

## Slices

| Slice | Goal | Files/Modules | Contracts/Data | Action | Verify | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Policy e registro | modelos, migration, runner_control, rotas, SDK/web | PolicyRevision, Runner, credencial hash | Owner cria policy/CAS e registra/desabilita runner; credencial sem read geral | papéis, revogação/expiry, segredo ausente em GET/log, CAS, migrations | sem policy habilitada ou runner aprovado não há dispatch |
| 2 | Planos e ledger | modelos, serviço transacional, rotas | plano selado, reserva, ledger append-only USD Decimal | reservar teto atômico antes de queued; limitar quota/paralelismo e política | disputa PostgreSQL entre projetos/execuções, idempotência, limites | reservas + gasto coerentes sob concorrência |
| 3 | Lease e terminalização | runner_control, rotas, SDK runner | attempt, lease token/expiry, heartbeat, cancel request/ack | lease único, TTL 60s/heartbeat 20s, revalidação e terminalização | duplicatas, revogação, fontes restritas, timeout, publicação tardia | incerteza não dispara nova chamada; terminal não é sobrescrito |
| 4 | Fixture runtime e web | runner cliente, fixtures, páginas, runbook | protocolo de dois turnos e tools fake | executar sem produção, documentar isolamento declarado, exibir orçamento/uncertain | PostgreSQL/Redis dedicados, morte após gasto, cancel durante tool, egress negado, E2E 375/1280 | evidências reproduzíveis locais; piloto externo continua separado |

## Dependencies

- PR #50 e F0–F3; artefatos/retention são outra entrega e não autorizam download por URL livre.
- Cada slice publica somente capacidades implementadas. Credencial de runner nunca cai no fallback de API key geral.

## Risk Gates

- API: schemas fechados, status técnicos separados de qualidade e erros sem identificação de recursos invisíveis.
- Data/migration: aditivo, legado preservado, hashes/manifests protegidos, downgrade recusado com evidência.
- Auth/security: project/env + fontes transitivas + principal/chave original + owner do runner + policy corrente em lease/publicação.
- External dependency: nenhum provider ou tráfego produtivo durante implementação; Redis/PostgreSQL somente descartáveis.
- Performance: quotas antes do trabalho; polling/leases limitados; sem varrer payloads secretos nem repetir chamadas incertas.

## Tests / Commands

- API focada por slice; matriz integral de rotas e papéis; full API no fechamento.
- SDK/CLI, web/typecheck/build e E2E nos fluxos novos; gates pesados sequenciais.
- Migration round-trip SQLite/PostgreSQL e corridas com schemas descartáveis em porta dedicada 15636.
- Fixture de isolamento com rede negada; registrar comando/resultado e limites reais do host, sem prometer sandbox gerenciado.

## Rollback

- Desabilitar dispatch por policy; não liberar reserva de gasto desconhecido para permitir rollback.
- Reverter código preserva manifests, ledger, leases e evidência tardia. Migration de downgrade não destrói evidência.
