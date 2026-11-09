# Ocultar trace e isolar sua origem em experimentos

Entrega D1, base `00e05e1`, sem mudança de contrato HTTP ou schema.

O detalhe oferece **Ocultar trace**, com confirmação, foco inicial em Cancelar,
ciclo de Tab, Escape, devolução de foco, estado pendente e erro seguro no diálogo.
A ação exige uma sessão pessoal validada, resolve o projeto e compara o projeto
do trace antes de enviar o DELETE com o token dessa sessão. Dados ocultos do
formulário não autorizam acesso; ambiente aceita somente vazio, dev, staging ou
prod, preservando também a ausência na volta à lista.

Ocultar é lógico: o trace sai da lista e o detalhe por trace fica indisponível.
Avaliações históricas, datasets, exports, auditoria e backups têm ciclos próprios.
Não há promessa de apagar essas cópias, nem purge, restauração ou alteração de
custos/cotas. O contrato existente segue DELETE 204 e segundo DELETE 404.

## Isolamento da origem

`_build_variant_context` agora consulta somente trace ativo no projeto do dataset.
`execute_experiment` recusa dataset de outro projeto. Assim o enriquecimento não
carrega metadados ou spans de outro projeto ou de trace oculto. O conteúdo já
pertencente ao item do dataset e seu expected_output permanecem independentes.

| Ator / entrada | Resultado verificado |
| --- | --- |
| Sessão pessoal e trace no projeto resolvido | DELETE com token pessoal, refresh da lista/detalhe e redirect |
| Somente bearer de desenvolvimento | Erro pedindo conta pessoal; nenhum DELETE |
| Chave read/ingest/evaluate, inclusive no header Bearer | API nega; trace e auditoria permanecem intactos |
| Usuário sem membership na organização | API 404, sem escrita |
| Trace de outro projeto adulterado no formulário | Ação nega antes do DELETE |
| Fonte de dataset de outro projeto ou ocultada | Sem enriquecimento da origem; cópia do dataset preservada |

## Evidências

- RED: teste da fonte mostrou vazamento de metadados nos negativos cross-project
  e soft-delete; o caso legítimo já passava. Guard de dataset divergente também
  reproduzido antes da correção.
- GREEN: 46 testes API, nos arquivos `test_experiment_source_isolation.py`,
  `test_hide_trace_contract.py`, `test_phase5_prompts_datasets_experiments.py`,
  `test_phase10_audit_privacy_exports.py` e `test_trace_actions.py`.
- Web: 256 testes Node, incluindo 20 que executam o TypeScript real da ação/API;
  `npx tsc --noEmit` e `npm run build` passaram.
- Playwright: sete cenários passaram com Next dev dedicado em 18160 e fake API
  local em 18161: 1280/375 px, confirmação, Cancelar/Escape/Tab, foco, retorno com
  ambiente vazio, sucesso, 401/403/404/500 com retry e fallback sem DELETE.
- Capturas 1280/375 inspecionadas: diálogo legível, controles visíveis e sem
  overflow. Detector Impeccable retornou `[]` no arquivo de UI alterado.

Backend usa SQLite temporário do conftest, fila ARQ falsa, rate limit em memória
e REDIS_URL apontando para porta local inativa explícita. Não há provider real.
PostgreSQL não foi necessário para filtros por coluna/NULL/JOIN; concorrência,
FKs e retenção física em PG não fazem parte desta evidência.

Para repetir o navegador, inicie em `apps/web`:

```sh
EVALOPS_API_BASE_URL=http://127.0.0.1:18161/v1 EVALOPS_DEV_MODE=1 EVALOPS_DASHBOARD_BEARER_TOKEN=dashboard-fallback npx next dev -p 18160
```

Em outro terminal no mesmo diretório:

```sh
E2E_BASE_URL=http://127.0.0.1:18160 E2E_HIDE_FAKE_API=1 npx playwright test e2e/hide-trace.spec.ts --workers=1
```

O teste sobe/encerra sua fake API e fica desativado sem a flag explícita.
Revisão independente é necessária antes de integrar a mudança de dados.
