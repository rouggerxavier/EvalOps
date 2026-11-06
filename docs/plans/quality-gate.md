# Quality Gate — plano da primeira entrega

## Objetivo
Controle de qualidade por projeto, demonstrável no overview e configurável em Settings.

## Fora de escopo
- Bloquear deployments, executar avaliações novas, alterar tracing/experiments ou criar outro pipeline RAG.

## Decisões
- Modo standard (agent-framework-router): persistência e ownership exigem testes de integração; sem risco destrutivo identificado.
- Uma configuração por projeto em tabela aditiva; GET sem efeitos colaterais, PUT substitui os cinco limites.
- Status calculado, sem persistir snapshots: pass, review por evidência ausente, fail por violação; fail prevalece.
- Janela 24h/7d/30d e ambiente iguais ao overview; somente traces não excluídos.
- Reutilizar consolidação RAG, cálculo p95 e condições automáticas executáveis das rubricas.

## Questões abertas
- Nenhuma bloqueante. Flags declarativas sem evaluator executável não serão tratadas como regras verificadas.

## Read first
- README.md; docs/README.md; auditoria front/back e revisão atuais.
- app/models.py, schemas.py, ownership.py, deps.py, db.py, Alembic.
- routes.py, routes_trace_actions.py, routes_evaluations.py, eval_service.py, parser.py.
- overview, settings, lib/api.ts, actions.ts, testes e CI existentes.

## Fatias
| Fatia | Objetivo | Arquivos | Contratos/dados | Ação | Verificação | Aceite |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Configuração/API | models, schemas, migration, router, serviços | GET/PUT /projects/{id}/quality-gate; GET /status | Persistir limites, consolidar métricas e razões | pytest API + migration | Isolamento, validação e pass/review/fail reais |
| 2 | Demonstração | overview, settings, componentes, API/actions, landing | Tipos e server action autenticada | Card PT-BR e formulário simples | Testes de render/action + build | Salvar e ver resultado na janela selecionada |
| 3 | Entrega | docs, testes, revisão | Compatibilidade existente | Testes de regressão, documentação e roteiro | suites backend/web, typecheck/build | Evidências e limites documentados |

## Dependências
- UI depende do contrato e da persistência da fatia 1.

## Gates de risco
- API: thresholds finitos, score/taxa 0–1, valores não negativos; razões estruturadas.
- Migration: criar apenas tabela nova; upgrade/downgrade em SQLite temporário.
- Segurança: get_owned_project para leituras e escrita; API key de ingestão não configura gate; archived/foreign retornam 404.
- Dependências: nenhuma dependência de produto adicionada.
- Performance: queries em lote para runs, scores, versões e spans; sem avaliação/LLM no GET.

## Testes / comandos
- pytest -q; npm run test; npx tsc --noEmit; npm run build.
- Testes do gate para boundaries, ausência de dados, filtros, reruns, regras críticas, persistência e ownership.

## Rollback
- Reverter código e aplicar downgrade somente após remover consumidores do gate. Downgrade remove exclusivamente configurações do gate.
- Nenhum dado dos módulos existentes é reescrito.

## Resultado do roteamento
```yaml
selected_mode: standard
reason: Feature aditiva em banco/API/UI, com contratos e ownership a verificar.
risk_factors: []
sensitive_areas: [tenant, migration]
fast_factors: []
complexity_factors: [backend e frontend, métricas compartilhadas, testes de regressão]
assets_selected: [task-mode-router, agent-framework-router, backend-slice-planner, diff-reviewer]
assets_skipped: [lifecycle persistente, agentes independentes, redesign amplo]
```
