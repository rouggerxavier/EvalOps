# R1 — permissões organizacionais no backend

Auditoria de access control e contrato de API, branch `fix/autorizacao-papeis`, base `00e05e1`, 2026-11-09. Escopo: deps, ownership, rotas não-auth, wrappers phase5, testes e este documento. Auth/session/password, schemas/modelos/migrations, workers, convites e UI estão fora desta fatia.

## Decisão e contrato público

A associação `Membership` do banco é a autoridade a cada request JWT. Claims `role` no JWT não concedem permissão. Papéis literais, sem normalização, conversão, promoção ou backfill:

| Papel DB | read | write operacional | admin | destructive |
| --- | --- | --- | --- | --- |
| owner | sim | sim | sim | sim |
| member | sim | sim | não | não |
| viewer | sim | não | não | não |
| qualquer outro valor | não | não | não | não |
| sem membership | não | não | não | não |

Sem membership ou recurso ausente/oculto: `404 not_found`. Membership sem capacidade: `403 forbidden`. Um papel legado continua armazenado e visível na listagem de membros acessível a papéis conhecidos; não recebe capacidades. `/me`, listar/criar organizações, autenticação/sessão e CLI judges conservam seus contratos próprios.

**Mudança intencional de compatibilidade:** member perde administração, incluindo criar/alterar projeto, listar/criar/revogar chaves, ler assinatura/uso e alterar quality gate/sampling. DELETE de trace e DELETE de chave exigem owner. Ações operacionais (prompts, versões, datasets, experimentos, avaliações/batch, feedback, flags, replay, criar exports, retry sampling, marcar notificações lidas) aceitam owner/member. A marcação de notificação é uma escrita compartilhada do projeto, não preferência pessoal. POST compare é read e valida ambos os traces.

API keys permanecem separadas de papéis: somente scopes/capacidades anteriores. PUT sampling ainda aceita chave evaluate, enquanto JWT exige owner. Rotas JWT-only continuam rejeitando chave isolada; ingestão e feedback por client ID continuam key-only. Nenhum endpoint de chave foi acrescentado ou retirado. Leituras de chaves, assinatura e uso são admin; as duas últimas podem criar registros, portanto a verificação precede esse efeito.

## Inventário e evidência

O [inventário executável TSV](../../apps/api/tests/fixtures/r1_route_permissions.tsv) registra cada método/path, permissão JWT e contrato de API key (`jwt`, scope, `only:scope` ou `public`). O gate compara essa lista estática com `app.routes` realmente registrado em processo limpo, incluindo rotas ocultas do OpenAPI. O processo separado impede que rotas artificiais adicionadas por outras suítes durante collection contaminem o inventário; nenhuma rota desconhecida é ignorada. Uma nova rota/método exige classificação e requests de teste. Exceções `own-contract` também são enumeradas explicitamente.

| Severidade / achado corrigido | Atacante → recurso / request | Correção e prova |
| --- | --- | --- |
| Alta: membership sem capacidade suficiente | viewer/legado da organização → projeto, chave, configuração, trace, dataset, prompt, export ou execução por GET/POST/PUT/PATCH/DELETE do inventário | loaders/deps verificam permission antes de mutações, reservas e enqueue; matriz HTTP integral com snapshot de todas as tabelas, captura DML e fila fake |
| Alta: autoridade administrativa excessiva | member → GET keys/subscription/usage, criar/alterar projeto, configurar ou excluir | admin/destructive somente owner; negações reais 403 sem efeitos |
| Alta: identificação de tenant por referência secundária | usuário do tenant A → trace/rubric/dataset do tenant B em JSON | loaders verificam todas as referências; compare valida os dois traces, bulk flag pré-carrega todos antes de escrever; testes 404 sem efeitos |
| Alta: papel antigo no token após rebaixamento | JWT emitido antes da alteração → batch/keys no request seguinte | membership DB por request; mesmo JWT negado após demotion, fila já autorizada preservada |

Assets: dados de traces/prompts/datasets/experimentos, chaves, orçamento/custo, jobs. Fronteiras: IDs de path/query/JSON → loaders; JWT → user autenticado → membership DB; API key → scope → projeto fixo. Todos os endpoints organizacionais têm veredito no inventário; auth e contratos próprios estão declarados fora da política organizacional.

A suíte própria verifica owner/member/viewer/legado/outsider, claims falsamente administrativos assinados, permissão inválida negada, ausência de DML/provider/export/reserva/enqueue nas negações, referências secundárias nas duas ordens com papel próprio de cada tenant, papéis com caixa/espaços não normalizados, leitura sem criação de registros (#30), scopes read/ingest/evaluate e mutações de API key que continuam permitidas. A suíte API completa e o SDK Python são os gates de regressão finais.

## Rollout, rollback e limites

Publicar R1 antes de introduzir viewers/convites. Comunicar a retirada explícita de administração de member; organizações sem owner ou com papéis desconhecidos exigem tratamento deliberado pelo operador. Nenhum dado real ou membership é corrigido automaticamente. UI ainda pode apresentar ações que o backend responderá 403; UI/convites pertencem a R2.

Rebaixamento vale no próximo request; trabalhos já autorizados podem terminar. Esta fatia não adiciona cancelamento retroativo nem serialização de mudanças de papel durante um request já iniciado. API keys existentes continuam com suas capacidades próprias, independentemente de quem as criou.

Rollback para uma versão sem esta política volta a conceder os privilégios antigos a members e não é seguro depois de introduzir viewers. Manter a barreira R1 ao reverter outras mudanças. Deploy/composição de lanes e revisão independente ficam a cargo do orquestrador; esta lane não publica.

PostgreSQL não é gate necessário nesta fatia: não há schema/migration/índice, JSON SQL novo, lock novo ou lógica de concorrência dependente de dialeto; a política usa SELECT de membership e comparações literais. Testes usam SQLite isolado por execução, TestClient sem lifespan e pool ARQ fake; nenhum Redis/LLM externo. Corridas de convite/transferência e último owner pertencem a R2.


## Revisão e verificação da lane

Veredito da revisão integrada: sem achado de implementação pendente no escopo de autorização. Revisão independente e composição continuam com o orquestrador.

Os testes novos protegem a matriz de papéis, isolamento de recursos e ordem de autorização antes de efeitos; os gates existentes verificam os fluxos administrativos e operacionais de owner e os contratos SDK. Não houve promoção de fixtures member para owner. O único ajuste em teste legado é `test_cross_project_eval_forbidden`: rubric de organização sem membership responde 404 em vez de 403, ocultando sua existência conforme o contrato R1.

Runner: `/Users/rougger/dev/EvalOps/.claude/worktrees/amostragem-20261108/.venv/bin/python`, `REDIS_URL=redis://127.0.0.1:16391/15`, `EVALOPS_RATE_LIMIT_BACKEND=memory`; pool ARQ fake do conftest. Comandos a partir da raiz da lane:

- `PYTHONPATH=apps/api python -m pytest -q apps/api/tests/test_membership_permissions.py apps/api/tests/test_phase4_rubrics_eval.py::TestEvalAPI::test_cross_project_eval_forbidden apps/api/tests/test_phase7f_rate_limit_service.py apps/api/tests/test_phase9_auth_hardening.py`: 92 passaram (72 próprios R1).
- `PYTHONPATH=apps/api python -m pytest -q apps/api/tests`: 720 passaram, 14 skips, 31 warnings, 74,51s; log local `/tmp/r1-full-api-20261109.log`.
- `PYTHONPATH=packages/sdk-python python -m pytest -q packages/sdk-python/tests`: 80 passaram.
- `git diff --check`: passou.

A primeira execução conjunta API+SDK teve 9 falhas, 768 passes e 14 skips: inventário contaminado por rotas artificiais de phase13, expectativa anterior 403 para rubric sem membership, três testes de rate limit usando Redis inativo e quatro asserts de caplog do SDK interferidos pela configuração de logger da API no mesmo processo. O inventário e a expectativa foram corrigidos; os gates dirigidos e SDK separado confirmaram as causas. Não houve alteração em produção para contornar o runner. A execução final de toda a API, isolada do SDK e com rate limiter em memória, passou integralmente; warnings de depreciação permanecem fora desta fatia.
