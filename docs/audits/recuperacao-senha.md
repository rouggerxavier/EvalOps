# Revisão da recuperação de senha

## Escopo

- Lens: access control; implementação e revisão pelo autor em 2026-11-09.
- Branch: `feat/recuperacao-senha`, base `00e05e1`.
- Rotas: forgot/reset públicos, troca autenticada que invalida pedidos, worker,
  persistência, limites Redis, configuração, limpeza e páginas web da recuperação.
- Fora de escopo: SMTP real, ingress de produção, RBAC, rotas de outros produtos,
  SDK e uma auditoria geral de autenticação. Revisão independente ocorre à parte.

## Veredito

As reproduções das revisões independentes foram corrigidas e cobertas por
regressões; a revalidação independente do novo commit está pendente. O delta passou
nos gates direcionados, build e fluxo real com caixa falsa. O gate completo da API
abaixo corresponde à versão anterior à revisão e não foi repetido neste delta.

## Entradas e ativos

| Entrada | Alcance | Ativo protegido | Fronteira |
| --- | --- | --- | --- |
| Email e IP observado | Forgot e limites Redis | Existência da conta e disponibilidade | Resposta uniforme; digest nos buckets |
| Token e senha nova | Reset público | Credencial e sessões pessoais | Token aleatório, hash persistido, TTL e consumo atômico |
| Fragmento e query | Página de reset | Token bruto | Fragmento removido, ref em memória, corpo da ação same-origin |
| Job e SMTP | Worker | Destinatário, link e envio | IDs opacos na fila, origem fixa e TLS verificado |

| Ator | Recurso / ação | Veredito |
| --- | --- | --- |
| Anônimo com email existente, inexistente ou sem senha | Solicitar recuperação | Público; mesmo 202 vazio e mesmos limites |
| Anônimo sem token, com token adulterado, expirado ou consumido | Alterar senha | Negado com `invalid_reset` fixo, sem escrita |
| Portador de token válido | Redefinir a conta vinculada ao digest | Permitido uma vez; não escolhe usuário nem versão |
| Sessão antiga após reset ou troca | Autenticar ou alterar senha | Negada pela versão da credencial |
| Origem externa | Invocar ação web de reset | Negada pelo Next antes da ação; sessão permanece válida |
| Job antigo ou duplicado | Enviar ou substituir pedido posterior | Sem efeito; claim durável impede reemissão |

## Achados e correções

O primeiro gate completo encontrou duas
falhas de caplog no replay: o teste novo da migration carregava `alembic.ini`, e
`fileConfig` desabilitava os loggers existentes do processo. O teste agora usa
`Config()` com `script_location` explícito, sem reconfigurar logging. A sequência
migration+replay reproduziu 2 falhas/2 sucessos antes e passou nos 4 casos depois,
mantendo as asserções de logs. Os limites operacionais conhecidos estão abaixo
e no [runbook](../ops/recuperacao-senha.md).

| Severidade | Reprodução independente | Correção e regressão |
| --- | --- | --- |
| High | Duas sessões SQLite leem pending e enviam dois emails | Claim CAS exige rowcount1 antes do commit/SMTP; duas sessões reais com barreira na geração do candidato agora enviam uma vez |
| Medium | IP bloqueado gasta três tentativas da conta de uma vítima | Retorno após IP negado precede conta; Redis dedicado mantém três tentativas disponíveis para outro IP |
| Medium | PG com timezone Fortaleza lê o mesmo instante em -03 e worker recusa job | Aware usa astimezoneUTC; teste real de sessão PG em -03 envia e consome o link |
| Medium | Reabrir hash no mesmo documento deixa campos desabilitados | Listener hashchange substitui token/erro; E2E válido→inválido→válido conserva Document e redefine senha |
| Medium | Next mantém token no history.state após remover URL | Saneamento de strings do estado opaco, replaceState nativo e PopStateEvent; E2E confere captura, erro, sucesso e Back |
| Low | Falha503 sugere aguardar minutos mesmo com feature desabilitada | Copy segura explica indisponibilidade e sugere tentar mais tarde ou contatar administrador, sem expor configuração |

As três regressões backend reproduziram falha antes e passaram após a correção.
As regressões web falharam no build anterior por token no histórico e hash não
consumido. A solução final passou no Next real; apenas replaceState(null) e
router.replace não bastaram, e as tentativas incompletas foram descartadas.

## Cobertura e verificações

A cobertura da revisão acrescenta três regressões backend e amplia o E2E para
reabertura no mesmo documento, histórico e cabeçalhos de requisição.

| Comportamento / falha | Evidência |
| --- | --- |
| Replay, expiração exata, substituição, rollback, reset×reset e reset×troca | Integração API em PG16 dedicado |
| Disponibilidade global antes do lookup; supressão e IP429; erro sem eco | Contratos de rotas e validação, inclusive root path |
| Duplicação, crash e falha de SMTP; fila sem email/token | Worker falso e ARQ com Redis dedicado |
| TLS, timeout, auth, origem fixa e injeção de destinatário | Testes do transporte sem conexão SMTP |
| Migration e limpeza | Upgrade→downgrade0013→upgrade→check em schema UUID; dry-run/idempotência; migration+replay 4 passaram após corrigir isolamento de logging |
| Unicode, validação e redirecionamento seguro | Node: 16 testes focados; suite web completa: 242 passaram |
| Integração web/API e sessões após revisão | Playwright Chromium: 4 passaram em dev/StrictMode e 4 em produção |
| Tipagem e pacote web | `npx tsc --noEmit` e `npm run build` passaram na retomada |
| Gate completo da API anterior à revisão | `pytest -q`: 696 passaram, 14 omitidos, 32 avisos, 74,19 s |
| Gate API do delta de revisão | Recovery + transport + change-password + migration + worker: 89 passaram, 2 avisos, 17,29 s, com PG16/Redis dedicados |

O gate final rodou somente `apps/api`, sem SDK no mesmo processo, com
`EVALOPS_RATE_LIMIT_BACKEND=memory`, `REDIS_URL=redis://127.0.0.1:18683/15`,
`RECOVERY_TEST_REDIS_URL=redis://127.0.0.1:18683/15` e o banco dedicado
`ACCOUNT_TEST_DATABASE_URL=postgresql+psycopg://evalops:evalops@127.0.0.1:15633/evalops_account_test`.

O E2E percorre login → forgot → caixa falsa → fragmento → confirmação inválida →
reset → login novo. Verifica token ausente de URL final, HTML, cookies, storages,
history.state, cabeçalhos e logs, recusa de origem externa, sessão antiga rejeitada
e replay inválido. Também cobre fragmento ausente/adulterado, query adversarial,
reabertura hash-only no mesmo documento, erro anterior limpo e Back.

A repetição local de E2Es esgotou a cota de IP loopback na primeira rodada dev
após a revisão. Foi removido somente o bucket do IP127.0.0.1 no Redis dedicado
18683/db15, preservando todos os buckets de conta, antes da execução dev final.
Nenhuma política de limite do produto foi desabilitada para o E2E.

A tentativa inicial de E2E em produção usou localhost como API e foi rejeitada
pela validação já existente de configuração. A execução final passou usando
loopback IPv4 mapeado (`[::ffff:127.0.0.1]`) apenas no ambiente local; nenhuma
regra de produção foi alterada. Um início do gate completo foi interrompido para
serializar com outra lane e não conta como verificação concluída.

## UI e acessibilidade

Veredito: sem achados visuais bloqueantes. Foram inspecionadas as quatro capturas
em produção e o código dos estados de envio, erro, sucesso e desabilitado. Labels
associados, erros ligados aos campos, status/alert e controles nativos preservam a
estrutura acessível. Não há rolagem horizontal nas larguras de 375 e 1280 px.

O teclado percorreu voltar → email → envio e voltar → nova senha → confirmação
→ envio. Os controles exibem foco visível; o campo medido usa contorno contínuo
de 2 px. Os tokens de cor herdados medidos contra o painel branco têm
contraste de 6,22:1 no texto auxiliar, 7,31:1 no erro e 12,44:1 no botão primário.

- [Forgot desktop](img/recovery-forgot-1280.jpg) e [mobile](img/recovery-forgot-375.jpg).
- [Reset desktop](img/recovery-reset-1280.jpg) e [mobile](img/recovery-reset-375.jpg).

## Risco residual e revisão humana

- SMTP foi somente simulado; entrega, credenciais e certificados reais dependem
  da implantação. A feature permanece desabilitada por padrão.
- Crash após claim durável pode perder email. O usuário deve pedir novo link.
- O IP observado pode ser o Next; a cadeia de proxies confiáveis precisa de
  configuração operacional antes de prometer limite por visitante.
- Nenhum leitor de tela ou aparelho físico foi usado. As verificações foram em
  Chromium local, código semântico, teclado, capturas e cores computadas.
- Publicação, push, PR e merge ficaram fora desta unidade.
