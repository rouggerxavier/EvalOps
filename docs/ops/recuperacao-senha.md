# Recuperação de senha por email

`/forgot-password` recebe o email; `/reset-password` permite escolher a nova senha.
O login oferece **Esqueci minha senha**. Não há login automático após redefinir:
todas as sessões pessoais anteriores perdem validade e a web exige novo login.
Chaves de API de projeto seguem o contrato de Conta e não são revogadas.

## Configuração e disponibilidade

A feature fica desabilitada por padrão. API e worker precisam das mesmas variáveis:

| Variável | Contrato |
| --- | --- |
| `REDIS_URL` | Redis compartilhado por instâncias API/ARQ; obrigatório, sem fallback em memória nesta recuperação |
| `EVALOPS_PUBLIC_ORIGIN` | Origem fixa da web, sem caminho, credencial, query ou fragmento; HTTPS em produção |
| `EVALOPS_SMTP_HOST`, `EVALOPS_SMTP_FROM` | Servidor SMTP e remetente |
| `EVALOPS_SMTP_PORT` | 587 por padrão; 465 usual em TLS implícito |
| `EVALOPS_SMTP_TLS` | `starttls` (padrão) ou `implicit`; TLS com verificação de certificado/hostname sempre |
| `EVALOPS_SMTP_USERNAME`, `EVALOPS_SMTP_PASSWORD` | Ambos preenchidos ou ambos ausentes, conforme relay |
| `EVALOPS_SMTP_TIMEOUT_SECONDS` | Timeout de conexão/operações SMTP; padrão 10s |

Configure segredos no mecanismo da implantação; não os cole em logs ou chat.
Os exemplos compose deixam SMTP/origem vazios e propagam a configuração para API
**e worker**. A web usa o `EVALOPS_API_BASE_URL` existente. Não existe fallback que
imprima um link ou token. Esta implementação foi validada somente com mailer falso;
nenhuma mensagem real foi enviada.

Ausência/configuração inválida de SMTP/origem/Redis retorna `503 recovery_unavailable`
global, antes de consultar a conta. O forgot também verifica a fila antes do lookup;
falha da fila ao enfileirar retorna503. Indisponibilidade Redis falha fechada. SMTP
inacessível durante o envio é assíncrono: o pedido já recebeu202, o token correspondente
é invalidado e o log registra somente categoria e IDs opacos. Monitore worker/fila
para detectar essa condição; o202 confirma aceitação, não entrega.

## Contrato público e proteção contra abuso

- `POST /v1/auth/forgot-password`, JSON `{ "email": "..." }`: `202` vazio para conta
  com senha, inexistente ou sem hash. Conta sem senha fica fora desta recuperação.
- `POST /v1/auth/reset-password`, JSON `token` + `new_password`: `204` vazio após
  redefinição. Token inválido, adulterado, expirado, ausente ou consumido recebe
  `400 invalid_reset`. Senha inválida/corpo inválido recebe erro fixo sem eco.
  Senha tem 8–256 codepoints Unicode, sem truncamento por unidades UTF-16.
- Limites Redis independentes: IP observado20/300s (429 e `Retry-After`), conta
  normalizada3/900s (supressão silenciosa202). Conta existe ou não, usa os mesmos
  buckets. Chaves guardam digest SHA256, nunca email/IP/token em claro. Cada registro
  usa MULTI/EXEC atômico. Janelas fixas permitem até cerca de2× ao cruzar a borda.
- IP já bloqueado encerra a verificação antes do bucket da conta; um atacante
  bloqueado não gasta a cota da vítima usando emails no corpo da requisição.
- O limite de reset também usa o bucket de IP, antes da consulta/hash de senha.
  Login/troca autenticada mantêm suas políticas existentes.

A API considera **somente `request.client.host`**, ignorando `X-Forwarded-For`,
`Forwarded` e `X-Real-IP` enviados pelo cliente. Next faz a chamada server-side,
portanto vários visitantes podem compartilhar o IP do Next e o limite conservador.
A implantação precisa estabelecer uma cadeia proxy/ingress confiável para preservar
IP visitante; esta fatia não implementa confiança em headers nem promete IP real.
Não configure o servidor ASGI para confiar irrestritamente em proxies externos.

O link usa exclusivamente a origem configurada: `/reset-password#<token>`. Nenhum
Host, Origin, return_to ou header encaminhado define o destino. O fragmento não vai
na requisição HTTP. O cliente captura/remove o fragmento e query do histórico após
montar e em `hashchange`, preserva em ref de memória sob StrictMode e envia somente
no corpo da Server Action same-origin. Também remove o token de strings no estado
JSON do histórico e sincroniza o roteador pelo evento nativo de navegação, sem ler
campos privados do Next. Reabrir um link na mesma aba substitui o token e o erro
anteriores, sem recarregar o documento. Não há cookie, local/sessionStorage ou
input oculto para o token.
Recarregar a página perde o token: reabra o email ou peça novo link. Páginas têm
no-referrer, noindex/nofollow e resposta no-store. Senha/token não retornam nos erros.

## Persistência, concorrência e falhas

Migration `0018_password_resets`, após `0017_runner_policy`: uma linha por usuário, request_id único,
versão esperada, status, timestamps e somente hashSHA256 único do token. A API
substitui o pedido anterior sob lock do usuário. ARQ recebe somente ID opaco do
usuário (aleatório no no-op), versão esperada, ID do pedido e instante do pedido.
Token bruto `secrets.token_urlsafe(32)` nasce no worker. Pedido pendente com mais de
30min não é enviado; token gerado tem TTL exato30min desde a geração, sem extensão
por retry. Um job antigo ou de versão antiga não substitui pedido posterior.

Antes do SMTP, worker reclama `pending`→`sending` com UPDATE condicional por
usuário/pedido/versão/status e exige exatamente uma linha alterada antes do commit.
O lock do usuário continua no PostgreSQL; o CAS também protege duas sessões
SQLite, onde FOR UPDATE é ignorado. Execuções duplicadas podem gerar candidatos
em memória, mas só a vencedora persiste o hash e envia a mensagem. Timestamps aware
são comparados no mesmo instante UTC, preservando sessões PG com timezone local.
**Crash após esse commit pode perder a
mensagem**, inclusive antes do envio; é o limite deliberado sem outbox/framework.
O usuário pode pedir novo link. Crash depois da entrega mantém o link válido até
uso/expiração. Falha SMTP marca `failed` e remove somente o hash daquele pedido;
completar/falhar um envio antigo não altera pedido novo.

Reset localiza o usuário pelo digest, bloqueia User, reconsulta o pedido, valida
hash/estado/expiração/versão e grava hash Argon2 + incremento da versão + exclusão
do pedido no mesmo commit. Antes do CAS da credencial, um DELETE condicional por
usuário/pedido/hash precisa reclamar exatamente uma linha; isso impede um token
substituído durante o hash de consumir o pedido posterior no SQLite. O hash é
calculado antes do primeiro write-lock SQLite e rollback preserva o pedido quando
o CAS da credencial perde. Reset×reset tem um vencedor; reset×troca serializa no
mesmo lock. A troca autenticada também exclui o pedido no commit. Rollback preserva
senha, versão e pedido. A manutenção existente inclui pedidos expirados em `all`,
ou `python -m app.maintenance.cleanup --target password-resets --dry-run` / `--apply`.

## Publicação e rollback

Aplique0018 antes das rotas/workers. Preserve o corte seguro de instâncias que
revalidam `credential_version` descrito em [Conta](conta-senha.md). Para desabilitar,
esvazie SMTP/origem; para remover código, drene jobs de recuperação primeiro.
Downgrade de0018 remove somente pedidos e links; não remova0013 nem o verificador de
versão após troca/reset real. Não rotacione/remova segredos de produção nesta sessão.

## Verificação isolada

```bash
cd apps/api
ACCOUNT_TEST_DATABASE_URL=postgresql+psycopg://evalops:evalops@127.0.0.1:15633/evalops_account_test RECOVERY_TEST_REDIS_URL=redis://127.0.0.1:18683/15 pytest tests/test_password_recovery.py tests/test_recovery_transport.py tests/test_change_password.py tests/test_worker_settings.py -q
cd ../web
node --test tests/recovery.test.mjs tests/account.test.mjs
npm test
npx tsc --noEmit
npm run build
```

As fixtures PG aceitam somente o banco dedicado em15633 e criam schema UUID;
Redis de integração aceita somente18683/db15. Nunca use6379 ou recursos compartilhados.
A migration deve passar upgrade→downgrade0013→upgrade→check em schema descartável.

O E2E é opt-in e usa exclusivamente uma caixa de entrada falsa em memória, sem
importar o transporte SMTP. Com os dois recursos dedicados acima ativos, inicie
em terminais separados:

```bash
cd apps/api
E2E_RECOVERY=1 ACCOUNT_TEST_DATABASE_URL=postgresql+psycopg://evalops:evalops@127.0.0.1:15633/evalops_account_test REDIS_URL=redis://127.0.0.1:18683/15 python tests/recovery_e2e_server.py
```

```bash
cd apps/web
EVALOPS_API_BASE_URL=http://127.0.0.1:18143/v1 npx next dev -p 3134
```

```bash
cd apps/web
E2E_RECOVERY=1 E2E_BASE_URL=http://127.0.0.1:3134 E2E_API_BASE_URL=http://127.0.0.1:18143/v1 npx playwright test e2e/recovery.spec.ts
```

O servidor falso cria e remove seu próprio schema UUID ao encerrar normalmente.
Encerre ambos os servidores após o teste. O gate final da API usa `pytest -q`
com `EVALOPS_RATE_LIMIT_BACKEND=memory`, `REDIS_URL` dedicado e as variáveis
`ACCOUNT_TEST_DATABASE_URL` e `RECOVERY_TEST_REDIS_URL` acima; ele também executa
o roundtrip da migration. Rode API e SDK em processos pytest separados para
preservar o isolamento de logging. Evidências e limites estão na
[revisão da recuperação](../audits/recuperacao-senha.md).
