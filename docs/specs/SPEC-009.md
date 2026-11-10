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

## Recursos compartilhados e origem dos dados

Norma para recursos novos: namespace é de projeto; visibilidade é limitada por access label da SPEC-002. Não é uma nova ACL humana por projeto: viewer/member/owner continuam autorizados pela Membership organizacional em todos os ambientes do projeto. Chave de serviço exige principal ativo, owner ativo, projeto exato, scope e seu único ambiente em allowed_environments, além de environment exato nos resultados. Scope sozinho não concede acesso à origem. Chaves antigas só entram nas rotas novas após associação explícita a ServicePrincipal e adesão aos mesmos checks, sem herdar permissão entre ambientes. Chave sem principal não acessa superfícies novas (403 service_principal_required), ainda que tenha read/evaluate legado.

Criação sem fontes referenciadas tem origin_environments=[ambiente declarado], allowed_environments=[esse ambiente]; upload deve declarar origem e auditoria registra que a declaração não é prova independente. Dados cujo label/origem é desconhecido são negados à automação até classificação humana. Para catálogo de modelo público ou dataset sintético independente de ambiente, somente owner humano pode declarar, **na criação**, origin_environments=[] e allowlist explícita de dev/staging/prod com justificativa e evidência dessa independência. Default nunca é all. Agente/member não podem autoatribuir origem neutra. Política inicial pode ser restringida, nunca ampliada automaticamente por cópia.

Com referências: origin_environments é união das origens, allowed_environments é interseção da allowlist solicitada com as de todas as fontes e do destino, calculada no serviço. Interseção vazia ou destino negado rejeita criação/referência (404 para fonte invisível; 422 para declaração inconsistente já autorizada). Fonte prod-only não se torna dev ao ser copiada, resumida, mascarada ou avaliada. Não há operação de desclassificação/republicação entre ambientes em F0/F1; eventual dado sanitizado exige processo separado e aprovação fora deste contrato. Nome, configuração, hash, external_ref e estatísticas também podem ser sensíveis: não expor um catálogo “só de metadados” negados.

Para evitar bypass pela API existente, **toda chave com ServicePrincipal** recebe enforcement de ambiente também nas rotas legadas que puder chamar (traces, prompts usados como evidência, feedback, reports, exports e downloads), sem mudar seus DTOs. Fonte Trace usa Trace.environment; recurso legado sem classificação/origem verificável é negado a essa identidade. A identidade humana e chaves antigas não associadas mantêm comportamento legado, que hoje valida projeto e não garante isolamento geral por ambiente. Portanto o rollout não pode anunciar isolamento de todas as chaves antigas; F0 exige principal novo restrito e testes contra bypass pelas rotas antigas antes de liberar uso por agentes. SDK não pode recorrer a token pessoal ou chave antiga para contornar negativa.

### Matriz de criação, consulta e referência

Todos os atores abaixo já passaram autenticação e pertencem à organização/projeto correto; referência fora do projeto da operação sempre retorna 404, mesmo entre projetos da mesma organização. Um humano com Membership pode selecionar outro projeto autorizado e operar nele, mas não vincular objetos de A a B. GET global humano autoriza pelo projeto do objeto; a chave continua presa ao seu projeto. Campos forbidden por scope/papel retornam 403 sem consultar conteúdo secreto.

| Recurso/operação | Owner humano | Member humano | Viewer humano | Chave dev (analogamente staging/prod) |
|---|---|---|---|---|
| Criar modelo/snapshot com origem dev | Sim | Sim com write | Não | read+write, fontes autorizadas e label dev |
| Criar origem prod-only | Sim | Sim com write | Não | Não, nem com scopes extras |
| Declarar catálogo/sintético independente de ambiente | Sim, justificativa registrada | Não | Não | Não |
| Consultar modelo/snapshot prod-only, itens e metadados | Sim | Sim | Sim | Não, 404 |
| Consultar recurso com allowlist dev+prod | Sim | Sim | Sim | read; permite dados completos classificados para dev |
| Referenciar recurso dev+prod em avaliação dev/prod | Sim no destino autorizado | Sim com write/evaluate | Não | dev: read+evaluate (read+write para criar PredictionSet); prod: não |
| Referenciar recurso prod-only em avaliação dev | Não sob esta política | Não | Não | Não |
| Restringir allowlist/revogar acesso de recurso | Sim, auditado | Não | Não | Não |
| Referenciar ID de outro projeto/organização | Não | Não | Não | Não |

Owner/member podem reutilizar modelo/snapshot autorizado em dev, staging ou prod **apenas se cada destino estiver na allowlist**. Para chave de cada ambiente a mesma regra é aplicada, sem token trocar environment. Recursos independentes autorizados aos três ambientes podem alimentar avaliações distintas; resultados, predições e comparação continuam isolados por ambiente. Cross-project/cross-org não tem sharing implícito nem por external_ref igual; importar outro projeto exige conteúdo fornecido por ator autorizado no destino, não dereference automática do ID original.

### Derivados, revogação e execução

Persistir source_refs e label em cada recurso derivado; Artifact é tão restrito quanto dono e fontes. Metadata, métricas agregadas, mensagens de erro, casos e investigações herdam restrições; não tratar agregação como anonimização. Acesso efetivo usa interseção do label salvo com permissões atuais de todas as fontes. Não ampliar label de resultado existente quando fonte é posteriormente reclassificada. Para prevenir corrida, criação/publicação valida versão de política na transação; versão mudou, reautorizar ou abortar sem publicar.

Revogação/expiração de chave bloqueia API imediatamente (401), desativação de principal/owner bloqueia uso, e token de lease não prolonga autoridade original: verificar parent key/principal/expiry/política no início, heartbeat e publicação. Jobs offline pendentes são cancelados por policy; em chamada externa já iniciada, registrar uncertain se efeito/custo não puder ser conhecido, sem publicar conteúdo ao ator revogado. Revogar chave não apaga dados: outro ator autorizado mantém acesso. Restrição/purge da fonte bloqueia derivados transitivamente, com tombstone para leitor autorizado; principal negado recebe 404. Idempotency receipts, caches, exports e downloads reautorizam cada acesso; não devolver resposta previamente autorizada após revogação.

Auditar criação, classificação inicial, restrição, referência, leitura sensível/download, bloqueio de worker, revogação e purge, com ator/chave/projeto/ambiente/policy_version/source IDs (acesso restrito), sem payload sensível. Workers chamam o mesmo serviço de autorização, nunca inferem permissão de um ID enfileirado.

### Aceite negativo obrigatório em serviço/API/worker

1. Chave dev+read+write+evaluate tenta GET/lista/digest/item/download ou avalia snapshot prod-only: 404, sem contagem, source ID ou payload vazado.
2. Snapshot permitido dev mas Artifact/source posteriormente restrito prod: nem leitura indireta de métrica/manifest, nem cache/receipt antigo escapa; worker não publica.
3. Chave dev tenta declarar origem neutra, alargar allowlist ou criar avaliação prod com snapshot compartilhado: 403 (papel) ou 404 (destino invisível), sem gravação parcial.
4. Misturar item dev-only e prod-only em snapshot dev retorna 404 sem expor qual item negado; nenhuma cópia é persistida.
5. IDs de modelo/snapshot/artefato de projeto B ou organização B usados como referência em request/run do projeto A retornam 404, mesmo para owner autorizado em ambos ou principal com todos os scopes. GET humano direto de B segue Membership de B; não é grant para criar vínculo cross-project.
6. Chave expirada/revogada após enqueue e antes de publicar: serviço recusa; job registra motivo policy auditável, sem tentativa paga automática. Download/receipt criado antes da revogação também recusa.
7. Mesmo principal dev chama rota legada de trace/report/export prod ou tenta usar chave antiga sem principal em rota nova: 404 no primeiro caso, 403 service_principal_required no segundo, sem fallback de SDK.
8. Controle positivo: recurso sintético criado por owner com allowlist dev/staging/prod é consultável por read de cada ambiente; produzir resultado dev não permite key prod ler esse resultado dev. Restrição posterior não muda hash/score histórico, mas impede acesso ao conteúdo derivado.

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
