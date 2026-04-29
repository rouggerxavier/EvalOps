# 17 — Risks, Tradeoffs & Open Questions

Living document. Atualizar continuamente conforme decisões são tomadas.

## 1. Riscos técnicos

### R-01 — Custo de LLM judge sai do controle em dev
**Probabilidade:** Alta. **Impacto:** Médio.
- **Mitigação:** cache de judge (hash input → output, TTL 7d); preferir Groq/Gemini Flash; cap por projeto + alerta a 80%.
- **Sinal precoce:** dashboard interno do autor mostra `judge_cost_usd_today`.

### R-02 — Schema de trace muda durante o MVP, quebrando clientes do autor
**Probabilidade:** Média. **Impacto:** Alto (autor não consegue instrumentar o portfólio).
- **Mitigação:** congelar shape do payload de ingestion na semana 2; mudanças posteriores são aditivas (nunca remover/renomear campo) durante o MVP.
- **Sinal precoce:** se duas migrations seguidas mexem em `traces` ou `spans` colunas, parar e revisar.

### R-03 — Auth.js v5 com gotchas em prod (cookie handling, edge runtime)
**Probabilidade:** Média. **Impacto:** Médio.
- **Mitigação:** spike de 1 dia na semana 1 para validar magic link + GitHub em ambiente preview; fallback para Clerk se múltiplos bloqueios.

### R-04 — RLS em Postgres atrapalha desenvolvimento
**Probabilidade:** Baixa. **Impacto:** Médio.
- **Mitigação:** RLS é defense-in-depth; código de service já filtra explicitamente. Rodar testes com role `app_user` que ativa RLS, usar role `app_admin` em migrations/scripts.

### R-05 — Worker síncrono no MVP gera latência inaceitável em ingestion com auto-eval
**Probabilidade:** Alta. **Impacto:** Alto.
- **Mitigação:**
  - **Default:** auto-eval **off** no MVP. Eval roda só por trigger explícito.
  - Caso usuário ative `auto_eval_rubrics`, ingestion responde 202 e dispara eval em background thread (não Arq, não DB queue) — best-effort, perde se servidor reinicia. **Documentar.**
  - Migrar para Arq na Fase 1.1 (semana 8).

### R-06 — `litellm` quebra com update breaking
**Probabilidade:** Média. **Impacto:** Médio.
- **Mitigação:** pin exato; CI testa upgrade antes de mergear; abstrair com interface fina `LLMClient` para trocar por implementação direta se necessário.

### R-07 — Volume de spans ultrapassa Postgres
**Probabilidade:** Baixa no MVP, alta em produção real.
- **Mitigação:** índice em `(trace_id)` + `(project_id, created_at)`; particionar por mês na Fase 2; ClickHouse para hot-path em Fase 3.

### R-08 — JSON gigantes em `messages_in/out` matam queries
**Probabilidade:** Média. **Impacto:** Médio.
- **Mitigação:** truncar com flag `_truncated=true` em ingestion (limite default 256KB); endpoint detalhe carrega JSONB completo só sob demanda.

### R-09 — SDK Python conflita com pydantic v1 do cliente
**Probabilidade:** Média. **Impacto:** Médio.
- **Mitigação:** SDK não depende de pydantic — usa `dataclasses` + `jsonschema` apenas. Cliente vê apenas `httpx` como dep transitiva.

### R-10 — Eval YAML mal formatado de cliente quebra worker
**Probabilidade:** Média. **Impacto:** Baixo (sandbox local ao request).
- **Mitigação:** validação strict no push; runtime errors viram `EvaluationScore.error`, run continua.

## 2. Riscos de produto

### R-20 — Produto fica "feio" demais para gerar wow em portfólio
**Mitigação:** investir 1 semana de polish (semana 7); usar shadcn templates de dashboard prontos; screenshot review por colegas designers.

### R-21 — Sobreposição com LangSmith / Langfuse / Phoenix dilui o pitch
**Mitigação:** posicionamento claro (ver `18-portfolio-positioning.md`): demonstra **construção** de plataforma LLMOps, não venda comercial. Diferenciais práticos: rubric-as-code YAML, integração nativa com 3 projetos do autor, regression-em-CI focado.

### R-22 — Marina (persona alvo) não acha o SDK fácil
**Mitigação:** usability test informal com 2-3 desenvolvedores antes do fim da semana 7.

## 3. Riscos de negócio (se virar SaaS)

### R-30 — LGPD/GDPR liability ao receber prompts com PII de clientes
**Mitigação:** ToS exige redaction quando aplicável; modo on_export por default no plano team; DPA template; opção self-hosted em Fase 2.

### R-31 — Concorrência de incumbentes (Datadog, New Relic) entrar no espaço
**Mitigação:** velocidade e foco em DX > breadth. Aceitar que produto sirva tier "abaixo do radar" deles.

### R-32 — Regulamentação de IA muda requisitos
**Mitigação:** schema com colunas para evidence/audit já preparadas; observar EU AI Act timeline.

## 4. Tradeoffs assumidos

| Decisão | Tradeoff | Quando reavaliar |
|---|---|---|
| Síncrono no MVP | Latência maior em ingestion com auto-eval | Fim da semana 7 |
| Postgres único para tudo | Limite de escala em ~10M spans | > 1M spans |
| Sem ClickHouse | Queries de drill-down ficam mais lentas em volume | Quando p95 query > 2s |
| Sem multi-region | RTT alto fora de gru/mia | Cliente fora da Américas |
| Sem RBAC granular | Usabilidade limitada para times grandes | Pedido explícito de cliente |
| Sem Stripe | Não é SaaS comercializável | Decisão estratégica |
| Sem TS SDK | DocOps/ImobiliarIA frontend não loga direto | Fase 2 |
| Editor YAML em vez de UI no-code | Curva para PMs | Persona Sofia reclamar |
| Pricing table manual | Update lento quando providers mudam preço | Mensalmente |

## 5. Open questions (consolidado)

### Produto
- [ ] **OQ-01.** Definir nome final (`EvalOps Studio` é codename). Marca, domínio, registro.
- [ ] **OQ-02.** Licença do código: MIT no SDK; backend/frontend a definir (PolyForm Noncommercial vs MIT vs Apache 2). Recomendação: **MIT** geral para portfólio, mudar se virar produto comercial.
- [ ] **OQ-03.** Posicionamento: alternative-to-LangSmith claro? Ou self-hosted-first? Recomendação: **self-hosted-friendly de origem**.

### Engenharia
- [ ] **OQ-10.** Aceitar payload OpenTelemetry nativo? Recomendação: **Futuro**.
- [ ] **OQ-11.** Compressão gzip no SDK? Recomendação: **opt-in quando batch > 50KB**.
- [ ] **OQ-12.** Tamanho máximo de mensagem? Recomendação: **256 KB / span; truncar com flag**.
- [ ] **OQ-13.** Suportar streaming de respostas LLM no SDK auto-instrument (capturar tokens corretos)? Recomendação: **sim**, é caso comum.
- [ ] **OQ-14.** ULIDs binários ou TEXT(26) na DB? Recomendação: **TEXT(26)** no MVP.
- [ ] **OQ-15.** Migração para particionamento de `traces` por mês — quando? Recomendação: **quando > 5M linhas**.

### Avaliação
- [ ] **OQ-20.** Rubricas suportam Python custom code (sandbox)? Recomendação: **não MVP**; sim em Fase 2 via `restrictedpython` ou subprocess.
- [ ] **OQ-21.** Calibration / agreement humano vs judge — UI dedicada ou notebook? Recomendação: **notebook MVP**, UI Futuro.
- [ ] **OQ-22.** Suporte a Reference-based evaluators (BLEU, ROUGE, METEOR)? Recomendação: **Futuro** (caso de uso restrito).

### Versionamento
- [ ] **OQ-30.** Editor visual de prompt no dashboard? Recomendação: **read-only no MVP**.
- [ ] **OQ-31.** Importer de prompts do LangSmith / Mirascope / DSPy? Recomendação: **Fase 2**.

### Segurança / Compliance
- [ ] **OQ-40.** BYOK (cliente fornece chave de criptografia)? Recomendação: **Fase 3 enterprise**.
- [ ] **OQ-41.** SSO SAML/OIDC? Recomendação: **Fase 3**.
- [ ] **OQ-42.** Self-hosted edition com licença comercial? Recomendação: **avaliar Fase 2**.

### Operacional
- [ ] **OQ-50.** Self-hosted via docker-compose como produto público? Recomendação: **publicar imagens Docker em Fase 2**.
- [ ] **OQ-51.** Helm chart? Recomendação: **não**.
- [ ] **OQ-52.** Multi-region? Recomendação: **Fase 3**.
- [ ] **OQ-53.** Webhook signing scheme — HMAC SHA-256 com timestamp? Recomendação: **sim**, padrão Stripe-like.

### Portfólio
- [ ] **OQ-60.** Vídeo demo: hospedar onde? Recomendação: **Loom + YouTube unlisted**.
- [ ] **OQ-61.** Página pública de marketing antes ou depois do MVP? Recomendação: **junto da semana 7** (parte do polish).

## 6. Premissas explícitas (assumptions)

Quando algo não foi explicitamente decidido, este projeto assume:

1. Autor (João) implementará sozinho em ~6-10 semanas, ~20h/semana.
2. Orçamento mensal de infra e LLMs durante MVP: **≤ USD 50/mês**.
3. Código comitado em repositório público GitHub do autor.
4. Documentação final renderizada como GitHub Pages (markdown).
5. Domínio `evalops.studio` será registrado (alternativa: `.dev`, `.app`, `.io`).
6. Idioma da UI no MVP: pt-BR (público de portfólio brasileiro). Migrar para EN antes de submeter ao público internacional.
7. Comunicação com providers LLM via SDKs oficiais ou `litellm` — sem provider proprietário inicial.
8. Pricing table de modelos atualizada manualmente até Fase 2.

## 7. Sinais para reavaliar este documento

- ≥ 2 itens da seção Riscos disparando juntos: revisar prioridade do roadmap.
- Open question recebe resposta concreta: mover para ADR ou doc específica e remover daqui.
- Premissa quebra (ex.: orçamento ultrapassado): documentar override.
