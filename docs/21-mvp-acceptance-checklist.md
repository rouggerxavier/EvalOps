# 21 - MVP Acceptance Checklist

Checklist objetivo para declarar o MVP do EvalOps Studio como concluido.

## 1. Product fit

- [ ] O produto demonstra tracing, avaliacao, regression e export em um fluxo
  coerente.
- [ ] O produto continua portfolio-first, mas com shape tecnico SaaS-ready.
- [ ] Pelo menos 1 projeto real do autor gera dados reais por >= 2 semanas.

## 2. Identity and multi-tenancy

- [ ] Usuario cria conta por magic link ou GitHub OAuth.
- [ ] Signup cria org default.
- [ ] Usuario cria ao menos 1 projeto.
- [ ] API key pode ser criada e exibida uma unica vez.
- [ ] API key fica persistida apenas como hash argon2id + prefix.
- [ ] Revogacao de key funciona.
- [ ] A API aplica isolamento por org/project.
- [ ] Existe teste cobrindo cross-tenant access denial.

## 3. Tracing and SDK

- [ ] `POST /v1/traces` aceita batch valido.
- [ ] Mesmo `client_trace_id` nao duplica trace.
- [ ] Trace persiste spans e events corretamente.
- [ ] Custos e tokens agregados batem com spans.
- [ ] SDK Python publica instrumentacao basica em poucas linhas.
- [ ] SDK nunca derruba a app cliente em erro de rede/servidor.
- [ ] `disabled=True` funciona como no-op real.

## 4. Dashboard MVP

- [ ] Project overview mostra KPIs basicos.
- [ ] Trace list suporta filtros essenciais.
- [ ] Trace detail mostra arvore de spans e conteudo relevante.
- [ ] Empty states ensinam a instrumentar.
- [ ] Navegacao principal autenticada funciona sem links quebrados.

## 5. Rubrics and evaluation

- [ ] Rubrica YAML valida pelo schema oficial do MVP.
- [ ] Nova versao de rubrica cria `version=n+1`.
- [ ] Os 7 evaluators MVP existem.
- [ ] `POST /v1/evaluations/run` roda manualmente e persiste `evaluation_run`.
- [ ] Score agregado e scores parciais aparecem no detalhe.
- [ ] Falha de evaluator individual nao mata a run completa.
- [ ] Budget/cost caps basicos sao respeitados.

## 6. Prompt versioning, datasets and experiments

- [ ] Prompt pode ser versionado.
- [ ] `prompt_version_ref` pode ser resolvido a partir do trace.
- [ ] Dataset pode ser criado e receber items.
- [ ] Experiment pode ser criado com variants e rubric.
- [ ] Regression suite manual retorna exit code correto.
- [ ] Relatorio de run e legivel para uso em CI/PR.

## 7. Feedback and export

- [ ] Trace recebe feedback via API.
- [ ] Feedback aparece no dashboard ou no trace detail.
- [ ] Export JSONL gera linhas validas.
- [ ] Export e compativel com uso futuro em HF/eval/fine-tuning.
- [ ] Usage counters refletem ingestion e eval.

## 8. Security and operations

- [ ] HTTPS/TLS previsto e configurado no deploy.
- [ ] Logs estruturados nao carregam prompts/respostas.
- [ ] Health endpoints existem.
- [ ] `/docs` OpenAPI existe e reflete a API atual.
- [ ] Sentry e metrics basicos estao conectados ou stubados claramente.
- [ ] Audit log cobre operacoes sensiveis minimas.

## 9. Testing quality bar

- [ ] Cobertura backend >= 70%.
- [ ] Existe teste unitario para cada evaluator.
- [ ] Existe teste de integracao para ingest happy path, idempotencia e parcial.
- [ ] Existe ao menos 1 E2E do fluxo login -> projeto -> key -> ingest -> trace.
- [ ] SDK roda na matrix Python 3.9-3.12.

## 10. Deployment and reproducibility

- [ ] `docker compose up` sobe o sistema local.
- [ ] Deploy hosted do web e da API esta estavel.
- [ ] Variaveis de ambiente estao documentadas.
- [ ] Migrations aplicam sem erro em ambiente limpo.
- [ ] Existe rollback plausivel para web/API.

## 11. Portfolio readiness

- [ ] README principal esta profissional e atualizado.
- [ ] README do SDK tem exemplo copy-paste.
- [ ] Existe video demo curto.
- [ ] Existe screenshot principal ou GIF.
- [ ] O roadmap restante esta publico e honesto.

## 12. Non-goals verified

- [ ] Nao foi introduzido worker obrigatorio no corte minimo do MVP.
- [ ] Nao foi introduzido Stripe real.
- [ ] Nao foi introduzido SDK TypeScript.
- [ ] Nao foi introduzido no-code rubric builder.
- [ ] Nao foi introduzido OTLP nativo como dependencia de MVP.
