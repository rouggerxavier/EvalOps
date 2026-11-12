# Convites e memberships R2

Emissão, listagem, revoke, PATCH/DELETE de membro e transferência exigem JWT
pessoal e owner atual da organização. Outsider recebe 404; papel sem capacidade,
403; anônimo e chave de projeto, 401. Aceite exige JWT, token aleatório de 256
bits, email atual de User e emissor ainda owner; falhas retornam uniformemente
400 `invalid_invitation`. Uma membership existente mantém literalmente seu papel.
O servidor deriva `permissions` ordenadas pela matriz R1 em aceite e resolve.

Cada mutação trava Organization primeiro e relê autoridade e alvos. PostgreSQL
usa NOWAIT (somente 55P03 vira 409); SQLite usa CAS de `membership_version` e
contenção reconhecida. Conflito exige novo pedido. Remoção/rebaixamento preserva
pelo menos um owner; transferência promove um membro/viewer existente e rebaixa o
emissor no mesmo commit. Alterações não mudam `credential_version` nem API keys.

Estados persistidos: pending → sending → sent/failed; accepted e revoked são
terminais. Apenas pending/sending/sent aparecem como expired após o prazo fixo de
24h contado da criação. Aceite aceita sending/sent e limpa o hash. Reemissão cria
outro ID e revoga convites abertos daquele email; remoção de membro também revoga
convites abertos para seu email atual. Revoke de accepted retorna 409 inclusive
após o prazo. GET nunca consome nem modifica o convite.

O worker recebe somente o ID e grava hash SHA-256 antes do SMTP, fora da transação.
Retries não enviam novamente. Finalização exige mesmo ID/status sending/hash;
ela não ressuscita accepted/revoked. Crash após claim pode perder a entrega: o
owner pode reemitir. Erro de enqueue compensa somente pending→failed sob lock;
se sending/sent/accepted/revoked estiver confirmado, retorna 202. Caso contrário,
503 é resultado incerto, sem garantia de que envio não começou. Sem retry oculto.
Tokens ficam só em memória, no corpo POST de aceite e no fragmento do email.
Respostas, auditoria, jobs e logs não incluem raw, hash ou link.

Na UI, linhas de owner não têm formulário de papel: rebaixar owner só acontece
por transferência. Papel desconhecido começa em "Manter papel atual (<papel>)",
opção desabilitada e obrigatória, então salvar sem escolha não envia PATCH.
Falha não reconhecida no aceite pede conferir o app antes de novo convite, sem
prometer acesso.

Lacuna conhecida: Ajustes mostra avaliação automática (sampling) somente com
`admin`. A API permite a member ler config/jobs (`read`) e repetir job
(`write`), mas a UI não oferece isso a member. Alinhar exige decisão fora de R2.

## Operação e rollback

`EVALOPS_INVITATIONS_ENABLED=false` é o default. Manter assim nesta rodada; não
configurar SMTP ou destinatários reais. A flag bloqueia apenas novos envios.
SMTP/TLS/origem e Redis reutilizam A2. O bucket distribuído
`invitation-issue:<org_id>:<owner_id>` permite dez pedidos por 300s e falha fechado.
Subir worker com a função nova antes de habilitar a emissão.

Antes de migrar dados existentes, executar somente leitura e registrar IDs:

```sql
SELECT o.id FROM organizations o
WHERE NOT EXISTS (SELECT 1 FROM memberships m
  WHERE m.organization_id = o.id AND m.role = 'owner');
SELECT organization_id, user_id, role FROM memberships
WHERE role NOT IN ('owner', 'member', 'viewer');
```

Não autopromover, normalizar papéis nem recuperar organização sem owner; essas
organizações precisam de tratamento deliberado. Papéis desconhecidos continuam
sem capacidades, e organização sem owner não tem ator autorizado a administrá-la.

A revisão 0020_organization_invitations segue 0019_execution_ledger; acrescenta tabela e versão sem alterar dados de R1/A2.
SQLite dev com create_all recebe a coluna pela compatibilidade idempotente já
existente em app/db.py; ambientes Alembic usam a migração.
Rollback operacional: desligar novos envios, pausar/remover somente jobs da função
por ID antes de retirar seu código, conservar schema e R1 (incluindo viewer).
A2+R1 continua seguro com os campos extras. Downgrade 0020 perde metadados de
convites e só pode ocorrer após parar consumidores e aceitar essa perda; não
reverte papéis concedidos, credential_version ou resets. Nunca limpar fila global.

## Provas dedicadas

Usar `MEMBERSHIP_TEST_DATABASE_URL` exclusivamente com PG16
`127.0.0.1:15634/evalops_membership_test`, usuário evalops, e
`MEMBERSHIP_TEST_REDIS_URL=redis://127.0.0.1:18684/14`. Os testes validam o alvo,
criam schemas com UUID e removem somente esses schemas/buckets UUID. Sem essas
variáveis, os testes PG/Redis ficam explicitamente skipped; SQLite não os substitui.
Não usar o alvo A2, Redis db0 ou dados reais.

```sh
python -m pytest -q tests/test_organization_invitations.py tests/test_membership_management.py tests/test_membership_concurrency.py tests/test_invitation_migration.py tests/test_invitation_transport.py tests/test_membership_permissions.py tests/test_worker_settings.py tests/test_recovery_transport.py
```

CI `migrate-postgres` executa roundtrip/check e as provas reais, além de upgrade.
O teste de concorrência usa dois engines e sessões independentes com barreira;
repetições são pedidos explícitos após um conflito controlado.
