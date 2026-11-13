# Prévia de exclusão

As prévias consultam o inventário de dados e dependências antes de qualquer
contrato de exclusão. Não removem registros, revogam credenciais ou cancelam jobs.
Todas retornam `execution_available: false`.

| Rota GET | Acesso |
| --- | --- |
| `/v1/projects/{project_id}/deletion-preview` | JWT pessoal de owner da organização do projeto |
| `/v1/organizations/{org_id}/deletion-preview` | JWT pessoal de owner da organização |
| `/v1/auth/me/deletion-preview` | JWT pessoal; apenas a própria conta |

Chaves de API não autenticam essas rotas. Um projeto arquivado continua visível
ao owner; para os demais papéis, responde como recurso inexistente.

O retorno inclui contagens, dependências, referências a arquivos gerenciados e
custos conhecidos por origem/período. Não inclui conteúdo de traces, prompts,
senhas, tokens, hashes ou caminhos de arquivos. A prévia da conta informa suas
memberships, quando ela é o último owner e referências que exigem uma decisão
antes da remoção ou anonimização da identidade.

Leases ativos aparecem como trabalho em andamento. Leases, attempts, relatórios
tardios e ledger entram no inventário e na contagem de registros protegidos
contra DELETE. Execuções uncertain e reservas unknown continuam sinalizando
possível gasto. O ledger impede exclusão direta de projeto/organização; a
prévia informa essa dependência e não tenta contorná-la.

Custos desconhecidos não são zero. As fontes de custo podem se sobrepor e não
devem ser somadas entre si. Custos de traces, avaliações e experimentos usam o
mês UTC de criação do registro; o gasto de execução usa a conta do período.
Reservas de orçamento não são tratadas como gasto conhecido.

O inventário não adquire locks de escrita. Mudanças concorrentes podem alterar
as contagens durante a consulta. Referências a arquivos não verificam sua
existência física, e a prévia não cobre backups ou cópias de terceiros. A
consulta da conta pode exigir varredura de colunas de atribuição sem índice.

Provas locais: `pytest -q tests/test_deletion_preview.py tests/test_membership_permissions.py`.
O CI também executa `pytest -q tests/test_deletion_preview.py -k pg_cost_periods`
no PostgreSQL16 aprovado, com um schema descartável por caso. O teste local
opcional aceita `DELETION_PREVIEW_TEST_DATABASE_URL` apenas em
`127.0.0.1:15637/evalops_deletion_test`; nenhum schema preexistente é removido.
