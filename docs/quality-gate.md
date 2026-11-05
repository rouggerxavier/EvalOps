# Quality Gate — controle de qualidade para agentes de IA

Implementado na primeira entrega de reposicionamento do EvalOps Studio. A base
LLMOps (tracing, evaluations, experiments, rubrics e RAG) continua sendo a fonte
de evidências. O gate adiciona uma decisão legível para quem opera agentes:
**Aprovado**, **Revisão necessária** ou **Reprovado**.

## Comportamento e arquitetura

- `quality_gate_configs`: uma configuração persistente por projeto, chave primária
  e FK `project_id`. Migração aditiva `0009_quality_gate_configs`, após `0008`.
- `routes_quality_gate.py`: autenticação JWT e `get_owned_project`, conforme as
  permissões existentes de Settings. Membros da organização podem ler e salvar;
  não é uma nova hierarquia de permissões. Projetos de terceiros, arquivados ou
  inexistentes retornam 404. API keys de ingestão não configuram o gate.
- `quality_gate_service.py`: calcula status a pedido, sem gravar snapshots, executar
  avaliações, chamar LLMs ou alterar traces. Score/custo/latência são resultados
  persistidos; resultados individuais continuam pertencendo a evaluations.
- `analytics_service.py`: p95 nearest-rank e cutoff compartilhados com overview.
- `rag_service.py`: detecção e consolidação RAG compartilhadas com listagem/detalhe.
  Valores zero de `support_rate`/`quality_score` são preservados, e números não
  finitos não são usados como evidência.
- `rubrics/outcomes.py`: condições de reprovação automática compartilhadas com o
  executor de avaliações. Uma condição ligada a um avaliador que falhou é crítica.
  Uma flag `auto_fail` levantada por um avaliador também é crítica.
- UI usa Server Components, API autenticada e Server Action; CSS puro e componentes
  Card/Badge existentes. A ação resolve o projeto autenticado pelos slugs da URL,
  em vez de aceitar um ID arbitrário enviado pelo formulário.

## API

| Método | Endpoint | Resultado |
| --- | --- | --- |
| GET | `/v1/projects/{project_id}/quality-gate` | Limites, `configured`, `updated_at` |
| PUT | `/v1/projects/{project_id}/quality-gate` | Substitui configuração, persiste e registra auditoria |
| GET | `/v1/projects/{project_id}/quality-gate/status?window=7d&environment=prod` | Métricas, status e razões estruturadas |

PUT usa unidades da API (score/taxa entre 0 e 1; USD; milissegundos):

```json
{
  "min_score": 0.8,
  "max_ungrounded_rate": 0.05,
  "max_avg_cost_usd": 0.05,
  "max_p95_ms": 2000,
  "require_zero_critical": true
}
```

Esses também são os defaults sugeridos. GET sem configuração não cria linhas;
`configured=false` mantém o resultado em `review` até salvar. PUT tem semântica
de substituição: campos omitidos voltam aos defaults, não preservam valores
anteriores. Valores negativos, não finitos, campos desconhecidos, taxas acima de
1 e p95 fracionário são rejeitados. p95 admite 0 a 86.400.000 ms.

Status usa a janela `24h`, `7d` (default) ou `30d`, pelo `Trace.created_at`, com
filtro opcional de ambiente, igual ao overview. Exclui soft-deleted traces.
A política pertence ao projeto; janela e ambiente são filtros de leitura.

## Definição das métricas

| Métrica | Cálculo | Evidência ausente |
| --- | --- | --- |
| Qualidade | Média dos aggregate_scores mais recentes por trace/rubrica; média dessas médias por trace | Review se algum trace não tiver avaliações completas |
| Alucinação / sem suporte | Média por trace RAG de `ungrounded/(grounded+ungrounded)`; sem claims usa `1-support_rate` válido | Review se algum trace RAG não tiver grounding; sem RAG é não aplicável |
| Custo médio | Soma de `Trace.total_cost_usd` dividida pelo número de traces | Review se não houver traces |
| p95 | Percentil nearest-rank de `Trace.duration_ms`, como overview | Review se não houver traces |
| Regras críticas | Número de traces com ao menos uma condição automática violada ou flag `auto_fail` levantada | Review se a exigência estiver ativa e faltar cobertura das regras |

A avaliação mais recente por **trace e rubrica** vence (desempate estável por ID).
Uma nova tentativa com erro/running não é escondida por um resultado antigo.
Avaliações com falha parcial, erros de avaliadores ou sem scores individuais não
aprovam qualidade. Erro do executor não é contado como violação crítica.
Um resultado abaixo do threshold de uma rubrica não é automaticamente crítico:
é preciso uma `automatic_fail_condition` ligada ao avaliador.

Limites são inclusivos: score igual ao mínimo e métricas iguais ao máximo passam.
Com configuração salva, qualquer violação medida gera `fail`, mesmo com outros
itens em revisão. Sem violações, qualquer evidência ausente/incompleta gera
`review`. Evidência completa dentro dos limites gera `pass`.
Desativar a exigência de regras críticas não desativa os outros quatro limites.

Cada razão contém `metric`, `status`, `code`, `observed`, `threshold` e
`sample_count`. Códigos atuais: `not_configured`, `missing_evidence`,
`incomplete_evidence`, `threshold_exceeded`, `within_threshold`, `not_applicable`.
Métricas não medidas são `null`, não zero. O frontend mostra amostra e limite de
cada item; não recalcula a decisão do backend.

## Demonstração para empreendedorismo

Problema: empresas adotam agentes de IA, mas precisam de evidência para saber
se eles atendem aos requisitos de qualidade e operação.
Proposta: transformar sinais técnicos em uma política de qualidade por projeto.
O diferencial desta entrega é a decisão integrada, configurável e explicável;
a apresentação não deve prometer uma categoria inédita de LLMOps.

1. Abra um projeto novo: o overview mostra **Revisão necessária**, sem evidências.
2. Em **Settings → Quality Gate**, salve 80% de score, 5% de respostas sem suporte,
   USD 0,05 por trace, 2.000 ms p95 e exigência de zero violações críticas.
3. Ingira um trace com `metadata.support_rate=1` e custo USD 0,01.
4. Execute uma rubrica com avaliador determinístico e regra automática:

```yaml
slug: atendimento-seguro
name: Atendimento seguro
description: Verifica o conteúdo permitido para o atendimento.
threshold: 0.8
evaluators:
  - id: resposta-segura
    type: regex_match
    config:
      target: trace.output.assistant_message
      pattern: '^Resposta segura$'
automatic_fail_conditions:
  - slug: resposta-insegura
    description: Resposta fora do conteúdo permitido reprova automaticamente.
    evaluator_id: resposta-segura
```

5. Com a resposta `Resposta segura`, volte ao overview: **Aprovado**.
6. Reduza o custo máximo para USD 0,005: **Reprovado**, com motivo em Custo médio.
7. Explique que tracing e evaluations permitem investigar a causa e comparar
   melhorias em experiments; o gate reúne as evidências para decidir.

O teste `apps/web/e2e/quality-gate.spec.ts` executa esse roteiro usando API, banco,
formulário, ingestão e rubrica reais, e verifica acesso aos módulos anteriores.
Cria uma conta/projeto de teste, sem alterar projetos existentes. Rode em ambiente
de desenvolvimento dedicado; não usa dados de produção.

## Executar e verificar

Ambiente existente: `cd apps/api && .venv/bin/alembic upgrade head`; se o projeto
usa `create_all`, o startup já cria a tabela adicional. Em produção, use a política
Alembic existente (`EVALOPS_USE_ALEMBIC=1`). Migração não altera tabelas anteriores.

```bash
cd apps/api
.venv/bin/pytest -q
PYTHONPATH=../../packages/sdk-python .venv/bin/pytest -q ../../packages/sdk-python/tests

cd ../web
npm ci
npm run test
npx --no-install tsc --noEmit
npm run build
npx --no-install playwright install chromium
# Com API e web locais em execução:
E2E_BASE_URL=http://localhost:3000 E2E_API_BASE_URL=http://localhost:8000/v1 \
  npx --no-install playwright test e2e/quality-gate.spec.ts
```

`E2E_SCREENSHOT_DIR` opcional salva imagens aprovado/reprovado/settings/mobile.
CI executa testes backend, SDK, testes unitários web e build; o E2E exige servidores
locais e é uma verificação adicional de demonstração.

Rollback: reverter consumidores do gate e depois `alembic downgrade
0008_export_jobs_file_size_bytes`. Isso remove somente configurações do gate.
Upgrade/downgrade/reupgrade foi testado em SQLite temporário e PostgreSQL 16
preservando projetos. No PostgreSQL, a remoção do projeto também confirmou o
`ON DELETE CASCADE` da configuração do gate.

## Limitações desta entrega

- Alucinação é um proxy de afirmações sem suporte, não uma garantia de verdade.
  Cada trace tem peso igual; não há inferência de grounding quando ele falta.
- Custo usa o total já registrado, incluindo as estimativas/defaults do pipeline
  atual. Zero registrado não garante custo real zero. Não inclui custo separado
  de execução das avaliações/judges.
- Regras por `flag` só contam como verificadas quando um avaliador registra a
  lista `flags` no resultado. Sem ela, pedem revisão quando a exigência crítica
  está ativa. Nenhuma classificação de segurança nova é inventada no gate.
- Sem amostra mínima configurável, alertas, histórico de decisões ou bloqueio
  automático de chamadas/deployments nesta primeira entrega.
- Leituras são em lote e a janela é limitada a 30 dias; agregação ainda ocorre em
  memória, como o overview. Não foi realizado benchmark em volume de produção.
- Migração e runtime verificados em SQLite e PostgreSQL 16, incluindo rollback
  e cascade. O E2E do gate também passou com PostgreSQL 16 e Redis reais.
  A validação local não substitui testes no ambiente de implantação nem um
  benchmark em volume de produção. Redis/replay foram cobertos pelas suítes
  existentes, não pelo navegador da demonstração.
