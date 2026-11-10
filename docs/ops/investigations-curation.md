# Investigações e curadoria

A web usa as mesmas entidades de API, SDK e CLI. Não executa modelos durante a curadoria. Saídas observadas de traces permanecem evidências; não são referências humanas por padrão.

## Fluxo humano

1. Abra Avaliações > Falhas observadas. Erro técnico e sinal legado de qualidade são categorias diferentes, sem decisão automática sobre o modelo.
2. Escolha um dataset e capture a evidência. Um owner precisa declarar a origem de datasets legados antes de acesso por automação. A classificação inicial é auditada e recusa fontes de ambiente incompatível.
3. Salve o caso em rascunho. A saída observada fica nos metadados; a referência esperada começa `null`.
4. Revise o caso, preencha a referência, marque revisada ou rejeitada e informe motivo. Essa transição exige usuário humano. Referências rejeitadas ou ausentes não viram valores zero.
5. Abra Investigações e registre evidências `tipo:ID`, hipóteses, resumo técnico e próximos passos. O mesmo ID retoma o estado. Histórico conserva autoria e revisões anteriores; a conclusão anotada não autoriza promoção ou execução.

## API e SDK

`POST /v1/projects/{project_id}/investigations` aceita `{environment,state}`; `GET /v1/investigations/{id}` retorna o estado atual. `PATCH` aceita `{state}`, exige `If-Match` com revisão decimal atual e `Idempotency-Key`. Histórico: `GET /v1/investigations/{id}/revisions`. Listas usam `limit`, `cursor` e `next_cursor`.

Casos usam `POST /v1/datasets/{id}/cases` e `PATCH /v1/datasets/{id}/cases/{item_id}`. O PATCH também exige revisão e chave de idempotência. Mesmo recibo e conteúdo devolvem a resposta original; outra edição com revisão antiga retorna 409. Use nova chave para nova operação e mantenha a chave em uma repetição após perda de resposta.

O SDK oferece `create_investigation`, `get_investigation`, `update_investigation`, `investigation_history`, `find_failures`, `get_trace_evidence`, `save_case`, `get_case` e `update_case`. Principais de serviço precisam de escopos read/write, projeto e ambiente compatíveis; não podem aprovar referências humanas.

## CLI

Defina `EVALOPS_API_URL` e `EVALOPS_API_KEY` no ambiente. O arquivo contém somente o objeto state, por exemplo `{"title":"Investigar resíduos","next_steps":["Revisar casos"]}`.

```bash
evalops investigation-create --project PROJECT --environment dev --file state.json --idempotency-key OPERATION
evalops investigation INVESTIGATION_ID --json
evalops investigation-update INVESTIGATION_ID --revision 1 --file state.json --idempotency-key NEXT_OPERATION
evalops investigation INVESTIGATION_ID --history --json
```

Código de saída: 0 sucesso, 1 falha de transporte/API, 2 entrada inválida. A CLI não transforma conclusão da investigação em decisão de qualidade de uma avaliação.

## Restrições e rollback

Fontes são revalidadas em cada leitura. Remover referência do editor não remove restrições acumuladas. Restrição ou exclusão da fonte pode ocultar investigação e histórico. Ciclos e referências entre projetos são recusados.

Migre com Alembic antes de iniciar banco existente. A migration 0015 é aditiva. Downgrade recusa dados de investigações ou recibos de revisões; preserve o banco para rollback de código. Testes locais usam fixtures, não comprovam valor de piloto externo.
