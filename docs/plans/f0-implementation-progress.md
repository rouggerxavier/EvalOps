# F0 e primeira vertical F1 — regressão offline

O PR #46 está integrado à main em `03a9032373d1cf691a421a1369f00a0a7f6ebb12`. As SPECs permanecem como referência normativa, sem reescrever suas propostas como evidência de execução. Esta implementação está na branch `feat/offline-regression-foundations`.

## Entrega implementada

| Área | Comportamento |
| --- | --- |
| Snapshots | Dataset tabular e casos editáveis; snapshot copia schema, input, referência, metadados e revisão. Canonicalizador v1 ordena sample_id/chaves e gera SHA-256 sem IDs/timestamps do recurso. Triggers SQLite/PostgreSQL protegem conteúdo materializado; restrição de acesso não reescreve hash. |
| Modelos e predições | Versões externas declaradas, proveniência partial e identidade única por projeto/nome/versão. Alterar conteúdo da mesma versão retorna 409. Importação de PredictionSet valida todas as linhas antes de gravar; IDs desconhecidos/duplicados não deixam importação parcial. |
| Métricas | Catálogo versionado de MAE/MSE/RMSE/R², resíduos, histograma e grupos por segmento. União tipada valida scalar/series/matrix, população, cobertura, normalização e estatísticas. R² negativo e RMSE acima de 1 permanecem intactos. Ausência, domínio inválido e overflow têm estados próprios; números não finitos são rejeitados. |
| Avaliações | Avaliação síncrona limitada usa status succeeded e decision=inconclusive/no_quality_policy. Métricas são persistidas uma única vez, sem traces artificiais nem passed. Consultas de evidências e maiores erros usam os fatos persistidos. |
| Autorização | ServicePrincipal pertence ao projeto e exige owner atual ativo. Chaves têm expiração obrigatória de até 90 dias e scopes read/write/evaluate separados. Projeto, ambiente do resultado e labels atuais de fontes transitivas são revalidados. Restrições propagam a derivados e recibos; listas paginam somente recursos acessíveis. |
| Idempotência e auditoria | Criações materializam recurso e recibo na mesma transação; mesma chave/body recupera o mesmo ID, body diferente retorna 409. Autorização precede recuperação. Criação/origem, revisão, restrição e leituras sensíveis geram auditoria sem payload de evidência. |
| Comparação | Experiment/ExperimentRun recebem discriminante, decisão e associação a TaskEvaluations. Recalcula métricas na população pareada, preserva resultados originais e política/hash imutáveis. Três pares ficam inconclusive com política padrão; fixture de 30 valida pass/fail descritivos. Casos críticos usam tolerância e referência humana revisada, com precedência própria. GET novo usa view=task_v1; DTO não contém passed. Legado mantém JSON/status/passed e não lista runs novos por default. |
| SDK e CLI | SDK usa HTTP com a mesma fixture/IDs/fatos; CLI discover/evaluate/result retorna JSON e distingue erro técnico de decisão. Credencial somente por ambiente. |
| Web | Em Avaliações, link Regressão offline cria dataset/snapshot/modelo ou reutiliza snapshot/modelo; aceita tabela manual e arquivo JSON. Exibe cobertura, validade, unidades, scatter de resíduos, histograma, maiores erros e tabela paginada. Compara versões consultando os mesmos runs da API. Não recalcula métricas ou decisões no navegador. |

## Limites e compatibilidade

- Regressão escalar offline; nenhum modelo, arquivo pickle, código ou provider é executado. Modelo declarado não significa identidade do produtor verificada.
- Importação JSON limitada a 10 mil linhas/10 MiB. Até oito segmentos e mil grupos por snapshot, com chave canônica de grupo limitada a 2.048 bytes, para limitar expansão de métricas. Capabilities publica os limites.
- Bordas do histograma ficam na configuração versionada do avaliador; default `[-100,-10,-1,0,1,10,100]`, na unidade do alvo. Bins incluem underflow/overflow, sem Infinity em JSON.
- Referências importadas são draft. Reviewed exige PATCH humano com If-Match, motivo e proveniência registrada; snapshot anterior não muda.
- Somente owner humano pode criar origem independente de ambiente com allowlist, justificativa e evidência explícitas. Cópias não ampliam acesso; snapshots compartilhados exigem allowlist explícita.
- Principals novos ficam bloqueados nas rotas legadas sem enforcement de origem. Chaves antigas mantêm seu comportamento legado e não acessam as superfícies novas. Não há fallback para token pessoal ou chave antiga.
- A união de métricas também valida matrizes de confusão como contrato; capabilities anuncia apenas o avaliador de regressão implementado. Não há treinamento/classificação executável, runner, investigação, MCP ou deploy automático.
- A comparação desta entrega é descritiva e post_observation; não afirma significância nem aprova promoção. Revisão de promoção/investigações permanecem nas fases posteriores.

## Verificação

Cobertura nova: fixture numérica e estados adversariais; hash e materialização; round-trip tipado; revisão/CAS; atomicidade de importação; matriz de autorização de todas as rotas novas; principals/revogação/scopes; origem neutra e restrições transitivas; referências entre projetos; triggers e FKs; SDK por socket HTTP real; comparação de três e 30 pares; migração com legado preservado; idempotência concorrente em PostgreSQL real.

E2E exercita a interface por teclado e arquivo, compara valores exatos dos elementos data com a API, reutiliza snapshot para uma segunda versão e consulta comparação em 375/1280 px. Asserções não substituem o DTO por passed=false.

Comandos:

```sh
cd apps/api
python -m pytest -q
# O alvo PG dedicado é validado no teste; sem a variável, esses casos são explicitamente skipped.
EVALOPS_OFFLINE_TEST_DATABASE_URL=postgresql+psycopg://offline_test:offline_test@127.0.0.1:15636/offline_test python -m pytest -q tests/test_task_migration.py tests/test_offline_task_postgres.py
python scripts/benchmark_offline.py --api-url http://127.0.0.1:18006/v1 --runs 20
cd ../../packages/sdk-python
python -m pytest -q
cd ../../apps/web
npm test
npx tsc --noEmit
npm run build
E2E_BASE_URL=http://127.0.0.1:3106 E2E_API_BASE_URL=http://127.0.0.1:18006/v1 npm run test:e2e -- e2e/offline-regression.spec.ts
```

O job migrate-postgres passou a executar alembic check e os testes reais de migration/concorrência, não apenas upgrade. Perfil CI full bloqueia integração; gates remotos referem-se ao SHA publicado. As execuções de benchmark e E2E usam a API de teste em sequência para não disputar escrita SQLite. Resultados finais serão registrados após conclusão dos gates.

## Rollout e rollback

Aplicar migration 0014 antes de iniciar a versão nova sobre banco existente; orientação em docs/ops/database-migrations.md. Backfill mantém legacy_synthetic e decision=null, sem reinterpretar resultados antigos.

Downgrade é bloqueado quando há dados novos. Rollback operacional mantém o schema aditivo, desabilita principals e suspende a interface nova. Não voltar a API antiga com chaves de principal ativas. A pasta .agent preexistente não integra esta alteração.

## Evidência local de encerramento

- Última suíte completa da API: **773 passed, 14 skipped**. Os skips são gates legados opcionais; PostgreSQL desta entrega executou de fato.
- Fechamento direcionado após os ajustes finais de autorização/contratos: **122 passed**, incluindo quatro gates de migration/PostgreSQL e matriz de rotas.
- SDK/CLI: **82 passed**. Web: **256 passed**, TypeScript sem erros e build de produção concluído.
- E2E completo: **2 passed** (1280/375 px), incluindo segunda versão sobre o mesmo snapshot e comparação inconclusive com três pares. A navegação usa comparison_run para não colidir com o parâmetro de flash legado run.
- Benchmark HTTP final otimizado: Python 3.12.3, macOS 27.2 arm64, SQLite local, 10 mil linhas, cinco execuções. Mediana **0,379 s** e p95 nearest-rank **0,398 s**, incluindo autenticação, fontes, cálculo, hashes e persistência. Exclui setup da fixture e GET de métricas; não é SLA de produção.
- Uma avaliação de domínio de 10 mil linhas teve pico de **17.466.500 bytes** rastreados por tracemalloc. A medição exclui construção das entradas, HTTP, autorização e SQLAlchemy; não representa RSS do servidor.

Uma execução anterior concorrente com E2E disputou o mesmo SQLite e excedeu o orçamento. O perfil também revelou validação recursiva repetida em campos numéricos já tipados; ela foi removida, mantendo validação recursiva nos campos JSON arbitrários e limites de finitude nos tipos numéricos. A medição final acima ocorreu sem concorrência de escrita no mesmo banco.
