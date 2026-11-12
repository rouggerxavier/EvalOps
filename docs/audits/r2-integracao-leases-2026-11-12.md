# R2 — composição com leases de F4

PR #55, head de entrada c5508fa, composto com a main917ea92 (PR #54).
Modo standard, CI full por incluir migrations e controle de acesso.

## Ajustes

- A composição original tinha duas heads (0020 e0021); upgrade head foi
  reproduzido recusando a ambiguidade antes do ajuste.
- A migration de convites, ainda não integrada, passa a0022 e depende de0021.
  O conteúdo da migration0021 já publicada permanece idêntico.
- O CI mantém as duas baterias PostgreSQL: leases/offline e convites/memberships,
  com Redis dedicado para os contratos de entrega de R2.
- O roundtrip de convites agora parte de0021 com execução uncertain, lease
  expirado, relatório tardio e ledger existentes. Upgrade, downgrade para0021
  e novo upgrade preservam todos esses registros e as proteções contra DELETE.
- O teste de downgrade recusado do ledger mantém o início explícito em0019 e a
  asserção exata de versão. A composição não afrouxa essa correção prévia de R2.
- Código e testes web permanecem idênticos ao head R2 revisado. O SDK e o
  protocolo de leases permanecem idênticos à versão integrada na main.

## Evidência local

- API dirigida:168 passed,59 skipped (PostgreSQL/Redis dedicados indisponíveis).
- Web:276 testes passaram; TypeScript sem erros.
- Alembic heads: somente0022_organization_invitations.
- Roundtrip SQLite verifica schema, constraints, identidade/memberships,
  password resets e preservação integral de evidências F4.
- Check global de schema continua obrigatório em PostgreSQL. SQLite verifica
  esta migration diretamente: autogenerate do legado acusa diferenças de
  reflexão em índice com expressão e default booleano, alheias a R2.
- Docker/sockets não estão disponíveis neste executor; não atribuir a esta
  rodada as execuções E2E/PG/Redis anteriores do PR.

## Gate de integração

O PR existente será atualizado sem force-push, verificando seu SHA anterior.
Merge exige todos os checks do novo head. Nenhuma emissão real, ativação de SMTP
ou alteração de flag produtiva faz parte da composição.

O rollback operacional de convites segue o runbook R2; downgrade0022 remove
metadados de convites e exige aceite dessa perda, mas não remove dados de leases
ou ledger da0021. Nenhum downgrade em dados reais foi executado.
