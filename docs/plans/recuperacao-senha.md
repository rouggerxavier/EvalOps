# Recuperação de senha — A2

## Objective
Recuperar conta com senha via email SMTP, token de uso único e novo login; standard.

## Scope
- In: auth público, tabela/migration 0018, Redis estrito, worker ARQ/SMTP, cleanup, forgot/reset web e configuração operacional.
- Out: email real nesta sessão, MFA, convites, RBAC, SDK, auditoria geral, redesign.

## Phases
| Phase | Work | Files/Modules | Verification | Exit Criteria |
| --- | --- | --- | --- | --- |
| 1 | Persistir pedido e consumir atomicamente | models, migration, auth, serviço | API + PG16 (replay, corrida, rollback) | Hash-only, User→token, versão e consumo no commit |
| 2 | Enviar uma tentativa SMTP por pedido | config, limiter, worker, cleanup | Redis dedicado + SMTP fake + duplicação/crash | Sem token/email nos jobs/logs e sem reemissão |
| 3 | Forgot/reset com fragmento | páginas, ações, forms | node, tsc, build, E2E | Token removido da URL e só em memória, erros fixos |

## Risks
- SMTP não oferece atomicidade com banco. Claim durável anterior ao envio evita reemissão; crash pode perder email e usuário pede novo link.
- IP observado pode ser o servidor Next. Usar somente request.client.host; operador deve definir ingress/proxy confiável antes de prometer IP visitante.
- Uma troca/redefinição invalida todas as sessões pessoais e links pendentes; chaves de projeto seguem o contrato A1.

## Rollback
Desabilitar SMTP/origem; remover rotas/UI/worker depois de escoar jobs. Downgrade 0018 remove somente pedidos de recuperação. Preservar coluna e verificador credential_version de A1.

## Acceptance Criteria
- 202 indistinguível por existência/sem hash; 503 global antes de lookup em dependências incompletas/indisponíveis.
- Token aleatório 32 bytes, hash SHA256 único, TTL exato 30 minutos; worker não regenera em retry.
- Reset204 e novo login; inválido/expirado/consumido sem eco de entradas; política Unicode8–256.
- IP/account distribuídos independentes; supressão conta202, IP429; Redis indisponível falha fechado.
- UI same-origin, fragmento só em memória e removido, no-referrer/noindex, sem mudança visual lateral.

## Resultado — 2026-11-09
- Implementação e revisão do autor concluídas; revisão independente coordenada à parte.
- API completa: 696 passaram, 14 omitidos; PG16 e Redis dedicados, migration up/down/up/check incluída.
- Web: 242 testes passaram; tsc/build passaram; Playwright 3/3 em dev e 3/3 em produção com caixa falsa.
- UI desktop/mobile, teclado, foco e contraste verificados. Nenhum SMTP real foi usado.
- Corrigido isolamento do teste de migration que desabilitava loggers do replay; sequência RED 2 falhas/2 sucessos → GREEN 4 sucessos.
- Evidências e limites: [revisão da recuperação](../audits/recuperacao-senha.md).

## Delta da revisão independente
- Claim CAS protege concorrência SQLite; lockUserPG preservado, timestamp aware normalizado pelo instante.
- IP bloqueado não consome bucket de conta. Três regressões backend RED→GREEN; gate dirigido 89 passaram.
- Reabertura hash-only substitui token/erro sem reload; token removido também do history.state do Next, sem campos privados.
- E2E real 4/4 em produção e dev/StrictMode; 16 testes Node focados, tsc e build passaram.
- Copy de indisponibilidade não promete minutos nem expõe configuração.
- FULL API anterior continua registrado; não repetido no delta para serializar CI. Novo commit aguarda revalidação dos dois revisores antes de publicação.
- Composição local com R1 `33a8384` (inclui D1/main `205e64c`): inventário classifica forgot/reset como own-contract/public e mantém requests anônimos. 166 testes API e 36 Node passaram; build e 4 E2Es em produção passaram na árvore composta.
