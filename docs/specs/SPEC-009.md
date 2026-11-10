# SPEC-009 — Segurança, governança e operação

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e reuso

Superfície de automação e runner amplia risco de gasto, acesso cruzado e efeitos externos. Atender owner, operadores, revisores e agentes com privilégio mínimo. Reusar Membership/ApiKey, ownership, rate limits, AuditLog, redaction, quotas e cleanup. Sem trocar auth inteira, prometer DLP universal ou executar migrações destrutivas.

## Identidade e permissões

ServicePrincipal(id,project_id,name,owner_user_id,disabled_at); ApiKey recebe service_principal_id opcional e env/expiry atuais. Chave nova de automação exige expiração <=90 dias e owner ativo; rotação com sobreposição explícita. Hash/segredo seguem mecanismo atual. Owner cria/revoga principal; revogação imediata na API e lease não renovável. Agente não usa JWT pessoal permanente. Chaves legadas sem principal mantêm comportamento atual, sem scopes novos implícitos.

| Permissão interna | Humano atual/futuro | Scope de automação novo |
|---|---|---|
| Ler projeto/evidências | viewer/member/owner da organização | read |
| Ingerir traces/predições | member/owner | ingest para traces; write para predições/casos |
| Editar dataset/caso | member/owner | write |
| Avaliar offline/traces | member/owner | evaluate |
| Executar adapter pago | member/owner dentro de política owner | execute + plano/limites |
| Configurar política/chaves | owner | sem grant padrão a agente |
| Apagar/exportar dados sensíveis | owner e confirmação | destructive/export dedicado, só mediante grant explícito |
| Aprovar crítico | owner humano | não disponível para service principal |

Papéis atuais são organizacionais, não prometer ACL por projeto a humanos. Chave continua restrita a um projeto/ambiente; toda leitura de ID filho resolve pai autorizado. `write`/`execute`/`export`/`destructive` são scopes propostos, rejeitados pelo schema atual. Legado `ingest,read,evaluate` preservado. Segredos de provider só no ambiente runner autorizado, nunca no manifest persistido.

## Interfaces e orçamento

POST/GET `/v1/projects/{p}/service-principals` e POST `/v1/service-principals/{id}/disable` owner; ampliar criação de key existente com principal e scopes. GET/PUT `/v1/projects/{p}/execution-policy` owner: ambientes, max_cost_per_run, monthly_budget, max_parallel, allowed_adapters, effects_policy, retention. Não reutilizar QualityGateConfig para permissão/orçamento.

Reservation ledger append-only: project_id/org_id/execution_id/attempt_id, currency USD, amount Decimal, kind reserve/settle/release/adjust, idempotency key, pricing_version, measurement_source. Transação bloqueia counter/ledger antes de reservar; soma de reservas+gasto não supera limite autorizado. Conciliar com UsageCounter/replay sem dupla contagem: novo ledger só para novas Execution; wrapper de replay só após testes de equivalência. Taxa e quota aplicadas antes de custo. Gasto unknown mantém reserva até operador conciliar; emitir evento, não liberar por timeout arbitrário.

## Privacidade, retenção e auditoria

Projeto define allowlist de campos coletáveis, redaction antes de persistência e retenção por classe. Default proposto: 30 dias raw evidence, 90 dias agregados/manifest, 365 dias audit sem payload sensível; implantação deve aprovar política/obrigações do tenant. Dados sintéticos podem usar política própria explícita. Campos removidos ficam com reason=redacted, não string vazia interpretável como falha de modelo. Redaction atual é opt-in e tools definitions persistem; revisar esse canal antes de afirmar proteção de PII completa.

Propagar purge por referências de trace, feedback, dataset editável, snapshots, predições, artefatos, caches e exports. Snapshot imutável não supera direito de exclusão: tombstone, hash/referência não sensível e indisponibilidade explícita, sem manter cópia bruta. Snapshots derivados entram em inventário de lineage. Ocultar não apaga; download expira e requer reautorização. Não manter presigned URL como evidência permanente. Hash pode ser dado correlacionável: não deduplicar cross tenant.

AuditLog estendido com actor_type/id, key_id, project_id, request_id, execution_id, manifest_hash, resultado e razão. Nunca body/segredo por default. Registrar criação/revisão/snapshot/importação/reserva/execução/cancelamento/purge/promoção humana. Eventos de mudança transacionais; export de auditoria só autorizado. Investigação armazena resumo público, não raciocínio privado do agente.

## Trust boundaries

Texto de traces/datasets é dado não confiável. Serializar/delimitar no judge, saída tipada e sem credenciais/tools; não transformar mensagem em instrução do sistema. Isolamento e autorização nos efeitos, não confiar em prompt para segurança. Judge calibrado contra casos revisados, registrar discordância, versão e amostra; referência criada pelo judge é draft. HTML/Markdown de evidência sanitizado; sem carregar imagens/URLs externas automaticamente. Nenhum código de evaluator enviado pelo cliente executa no API worker.

## Confiabilidade e operação

Estados SPEC-001 e leases SPEC-005; categoria de erro separa dado/modelo/avaliador/infra/policy. Métricas operacionais: queue age, running age, orphan leases, failure by category, unknown spend, coverage, p95 avaliação e storage. Logs estruturados com IDs, sem PII. Runbook futuro cobre worker morto, reconciliação de custo, revogação, purge e restauração. Backup/restore inclui blobs e manifests coerentes, tombstones reaplicados após restore.

## Dependências e migração

SPEC-001 transversal; subset de ownership/scopes/audit/limites obrigatório antes da vertical SPEC-002/003/004. Ledger/leases antes de SPEC-005; retenção de artefatos antes de SPEC-006. Expand e backfill sem elevar papéis desconhecidos; preservar deny-by-default de deps.py. Nunca registrar IDs de migration até reconciliar head real.

## Testes, riscos, aceite e plano

Matriz negativa cobre org A/B, project A/B e todos os filhos/artefatos/worker. Testar revogação, usuário owner removido, corrida de reserva, replay idempotente, logs sem segredos, prompt injection e SSRF por URL de artefato. Redaction/purge alcança cópias derivadas e export; tombstone explica evidência indisponível. Teste de restore em ambiente dedicado antes de rollout de retenção.

Risco residual: provider pode cobrar após interrupção; declarar custo incerto. Ambiente de runner cliente pode não conter código hostil; capacidade deve ser explícita. Avaliador pode errar; inconclusive/revisão humana são obrigatórios quando evidência falta.

1. Identidade/escopos/auditoria e isolamento da vertical.
2. Retenção/artefatos e purge derivado.
3. Ledger, planos e leases para execução paga.
4. Operação/restore e piloto adversarial antes de runner hospedado.
