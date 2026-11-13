# D3: prévias de exclusão

## Escopo e origem

Entrega de três GETs de inventário: projeto, organização e própria conta.
`execution_available` permanece falso; não há endpoint de execução de exclusão.
A implementação anterior vem de `feat/exclusao-preview` `96cf4f8`, já composta
com main `b9bc2a2`. As alterações locais recentes de serviço/testes foram
copiadas para uma cópia Git isolada; a worktree original permanece intacta.

A composição usa a correção de attempts do PR #56. O delta de D3 preserva o
protocolo de leases e as migrations publicadas, acrescentando:

- Leases e relatórios tardios no inventário e nos testes de evidências reais.
- Leases ativos nas dependências de trabalho em andamento.
- Contagem de DELETE bloqueado para ledger, leases, attempts e relatórios.
- Prova PostgreSQL16 de períodos UTC em dois fusos, agora incluída no CI.
  Cada caso cria seu próprio schema e remove apenas esse schema ao terminar.

## Verificação e revisão integrada

`pytest -q tests/test_deletion_preview.py tests/test_membership_permissions.py`:
**93 passed / 2 skipped**. Os dois skips exigem PostgreSQL e são executados
explicitamente no job `migrate-postgres` desta entrega.

As provas cobrem owner/member/viewer, projeto arquivado, ausência e outro tenant,
conta própria, API keys recusadas, ausência de escrita e de segredos nas
respostas, além de um grafo real com execução concluída, lease ativo, relatório
tardio e gasto liquidado. As contagens de registros protegidos incluem attempts
sob a nova migration0023.

Self-review: consultas restringem conteúdo ao escopo do projeto/organização ou
à atribuição da própria conta; DTOs expõem agregados; três novas rotas constam
da matriz de autenticação/permissões. Nenhum arquivo de ambiente, segredo,
ativação produtiva ou alteração de UI entra no delta.

## Integração e limites

Modo standard; CI targeted para o delta de API/permissões, com a pipeline
existente completa preservada e o gate PostgreSQL adicional. A publicação espera
o merge do PR #56; os gates do SHA final de D3 continuam obrigatórios.

MERGE BLOCKER: CI do head composto, incluindo os dois fusos em PostgreSQL.

NEXT-WORK BLOCKER: nenhum para leitura, documentação e preparação de outra unidade.

POST-MERGE OBSERVATION: observar CI da main; falha posterior exige investigação.

Limitações aceitas: inventário pode mudar por concorrência; scans de atribuição
da conta e de certas FKs podem ser custosos; nenhuma política de exclusão,
anonimização, reconciliação financeira ou remoção de backups é definida aqui.
O contrato e os comandos operacionais estão em `docs/ops/deletion-preview.md`.
