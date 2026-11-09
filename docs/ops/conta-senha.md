# Conta e troca autenticada de senha

`/account` exige um cookie de sessão pessoal validado pela API; o bearer de
fallback do dashboard não abre essa página nem autoriza a Server Action.
O link **Conta** aparece na barra ativa do workspace, com **Sair** preservado.

`POST /v1/auth/change-password` usa o JWT Bearer como única autoridade sobre o
usuário. O JSON recebe `current_password` (1–256 caracteres) e `new_password`
(8–256 codepoints Unicode). A recuperação pública e sua configuração estão em [recuperação por email](recuperacao-senha.md).

- `204`: hash Argon2 e versão da credencial alterados na mesma transação. Todas as
  sessões pessoais anteriores, inclusive a usada na troca, recebem `401` nos
  próximos pedidos. A web apaga o cookie e exige entrada com a nova senha.
- `400 invalid_credentials`: senha atual incorreta ou conta sem hash de senha.
- `401 unauthorized`: JWT ausente, inválido, revogado ou versão desatualizada.
- `422 invalid_password`: corpo inválido; nenhum valor enviado retorna no erro.
- `429 too_many_attempts`: cinco tentativas por usuário a cada 300 segundos, antes
  de executar Argon2, com `Retry-After`. Usa o backend de rate limit já configurado;
  o fallback em memória é por processo, inclusive durante indisponibilidade do Redis.

Senhas seguem apenas no corpo do POST, nunca em URL, query ou logs. A ação web
mantém a verificação de origem do Next. As chaves de API continuam pertencendo ao
projeto; trocar a senha pessoal não as revoga.

## Schema, publicação e rollback

A migration `0013_user_credential_version`, após `0012_evaluation_sampling`,
adiciona `users.credential_version INTEGER NOT NULL DEFAULT 0`. Usuários existentes
começam em zero. SQLite local também recebe a coluna pelo caminho idempotente de
compatibilidade no startup/seed, sem apagar ou recriar dados.

JWTs novos incluem `credential_version`; login, cadastro e seed dev usam a versão
atual do banco. Um JWT legado sem a claim equivale a zero e só funciona enquanto o
usuário ainda está na versão zero. O verificador exige inteiro estrito, sem aceitar
booleano, string, float ou `null`. A troca relê o usuário sob `FOR UPDATE` com
`populate_existing`; o UPDATE também condiciona a versão anterior para impedir
perda de atualização no SQLite.

**Não misture instâncias que ignoram a versão com instâncias que já permitem a
troca.** Código antigo revalidaria sessões revogadas. Aplique primeiro a migration;
depois substitua todas as instâncias antigas antes de liberar tráfego para a nova
rota (janela de manutenção ou corte de tráfego). Outra opção é implantar primeiro o
verificador de versão em todas as instâncias e só então habilitar a troca. Inclua
workers/processos que autentiquem JWT no corte.

Após a primeira troca real, não execute downgrade dessa coluna nem reduza versões.
Um rollback seguro mantém a coluna e o verificador, mesmo que remova a UI/rota de
troca. Para retornar a código que ignora a versão, é necessário encerrar globalmente
os JWTs por rotação coordenada de `JWT_SECRET`, removendo instâncias com o segredo
antigo antes de reabrir tráfego. A troca do segredo afeta todas as sessões pessoais.
Os comandos de downgrade abaixo foram usados somente no banco descartável de teste.

Pedidos já autorizados antes da troca podem terminar; a revogação é conferida em
cada autenticação seguinte. Quem esqueceu a senha pode usar a recuperação por email quando SMTP, origem pública e Redis estiverem configurados.

## Verificação local

A suíte normal da API usa SQLite temporário pelo `conftest.py`; informar apenas
`DATABASE_URL` não a transforma em integração Postgres. Os testes dessa fatia têm
uma fixture própria, com engine/sessões próprias, schema aleatório e guarda que
aceita apenas o Postgres 16 dedicado em `127.0.0.1:15633/evalops_account_test`.

```bash
cd apps/api
pytest tests/test_change_password.py -q
ACCOUNT_TEST_DATABASE_URL=postgresql+psycopg://evalops:evalops@127.0.0.1:15633/evalops_account_test pytest tests/test_change_password.py -q
```

Contra o mesmo banco descartável, com `DATABASE_URL` explícita: `alembic upgrade
head`, `alembic downgrade 0012_evaluation_sampling`, novo `alembic upgrade head` e
`alembic check`. Nunca use um banco pessoal/produção para esse ciclo.

Os testes de navegador são opt-in e criam contas descartáveis na API indicada:

```bash
cd apps/web
E2E_ACCOUNT=1 E2E_BASE_URL=http://127.0.0.1:3133 E2E_API_BASE_URL=http://127.0.0.1:18133/v1 npx playwright test e2e/account.spec.ts
```

Execute somente com API/web e banco isolados. A evidência desta implementação,
incluindo limites e capturas, está em [auditoria da fatia Conta](../audits/conta-senha-2026-11-09.md).
