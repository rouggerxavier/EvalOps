# Revisão da recuperação de senha

## Escopo

- Lens: access control; implementação e revisão pelo autor em 2026-11-09.
- Branch: `feat/recuperacao-senha`, base `00e05e1`.
- Rotas: forgot/reset públicos, troca autenticada que invalida pedidos, worker,
  persistência, limites Redis, configuração, limpeza e páginas web da recuperação.
- Fora de escopo: SMTP real, ingress de produção, RBAC, rotas de outros produtos,
  SDK e uma auditoria geral de autenticação. Revisão independente ocorre à parte.

## Veredito

Não foram encontrados bloqueadores na revisão do autor. Os gates direcionados,
o build, o fluxo real com caixa falsa e o gate completo da API passaram.

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

Nenhum achado aberto nesta revisão. O primeiro gate completo encontrou duas
falhas de caplog no replay: o teste novo da migration carregava `alembic.ini`, e
`fileConfig` desabilitava os loggers existentes do processo. O teste agora usa
`Config()` com `script_location` explícito, sem reconfigurar logging. A sequência
migration+replay reproduziu 2 falhas/2 sucessos antes e passou nos 4 casos depois,
mantendo as asserções de logs. Os limites operacionais conhecidos estão abaixo
e no [runbook](../ops/recuperacao-senha.md).

## Cobertura e verificações

A cobertura existente na unidade protege os riscos relevantes; a retomada não
adicionou testes redundantes. Ela concluiu E2E e inspeção da UI e revisou o diff.

| Comportamento / falha | Evidência |
| --- | --- |
| Replay, expiração exata, substituição, rollback, reset×reset e reset×troca | Integração API em PG16 dedicado |
| Disponibilidade global antes do lookup; supressão e IP429; erro sem eco | Contratos de rotas e validação, inclusive root path |
| Duplicação, crash e falha de SMTP; fila sem email/token | Worker falso e ARQ com Redis dedicado |
| TLS, timeout, auth, origem fixa e injeção de destinatário | Testes do transporte sem conexão SMTP |
| Migration e limpeza | Upgrade→downgrade0013→upgrade→check em schema UUID; dry-run/idempotência; migration+replay 4 passaram após corrigir isolamento de logging |
| Unicode, validação e redirecionamento seguro | Node: 16 testes focados; suite web completa: 242 passaram |
| Integração web/API e sessões | Playwright Chromium: 3 passaram em dev e 3 em produção |
| Tipagem e pacote web | `npx tsc --noEmit` e `npm run build` passaram na retomada |
| Gate completo final da API | `pytest -q`: 696 passaram, 14 omitidos, 32 avisos, 74,19 s |

O gate final rodou somente `apps/api`, sem SDK no mesmo processo, com
`EVALOPS_RATE_LIMIT_BACKEND=memory`, `REDIS_URL=redis://127.0.0.1:18683/15`,
`RECOVERY_TEST_REDIS_URL=redis://127.0.0.1:18683/15` e o banco dedicado
`ACCOUNT_TEST_DATABASE_URL=postgresql+psycopg://evalops:evalops@127.0.0.1:15633/evalops_account_test`.

O E2E percorre login → forgot → caixa falsa → fragmento → confirmação inválida →
reset → login novo. Verifica token ausente de URL final, HTML, cookies, storages
e logs, recusa de origem externa, sessão antiga rejeitada e replay inválido.
Também cobre fragmento ausente/adulterado e query adversarial.

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
