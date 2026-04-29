# 13 — Security, Privacy & Compliance

## 1. Threat model (resumido)

| Ator | Objetivo | Mitigação principal |
|---|---|---|
| **Cliente externo** instrumentando seu app | Vazamento de dados de outro tenant | RLS por org, repository layer enforced, queries cobertas em testes |
| **End-user do app cliente** | Acessar trace alheio via API key vazada | API key tem scope `ingest`, não `read`; tokens efêmeros para dashboard |
| **Atacante na rede** | Interceptar trace em trânsito | TLS 1.3 obrigatório |
| **Atacante com acesso físico ao DB (insider)** | Ler API keys ou prompts | Hash argon2id em keys; encryption at rest do DB; logs sem conteúdo |
| **Bot/scraper** | DoS na ingestion | Rate limit por key + IP; tamanho máx 1MB por request |
| **Cliente malicioso** | Poluir trace de outro projeto | API key bound a projeto; queries SEMPRE filtram por project_id da key |

## 2. Autenticação

### 2.1 Usuários (dashboard)
- Auth.js v5 com:
  - Email magic link (default).
  - GitHub OAuth.
- Sessão em cookie HttpOnly + Secure + SameSite=Lax.
- Sessão server-side em DB (`sessions` table do Auth.js).
- Inatividade: 30 dias.
- Logout invalida sessão imediatamente.

### 2.2 API keys (apps clientes)
- Geradas no formato: `evk_{env}_{36 random chars base62}`. Ex.: `evk_live_a1b2c3d4e5f6...`.
- **Prefix** (`evk_live_a1b2c3`, primeiros 14 chars) é stored em claro para identificação.
- **Hash** (argon2id, parâmetros: m=19MiB, t=2, p=1) é stored.
- Em validação: lookup por prefix → verify hash. **Não** armazenamos LRU em claro; cache de validação só salva `(hash → ok)` em Redis com TTL 60s.
- Revogação: `revoked_at = now()`. Cache invalidado por publish em Redis.

### 2.3 Inter-service
- Workers chamam o backend via REST com token JWT de serviço (RS256, kid em header), gerado com chave privada ENV.

## 3. Autorização

### 3.1 Roles (MVP)
- `owner`: tudo na org, incluindo billing.
- `admin`: tudo exceto billing.
- `member`: ler/escrever projetos onde for adicionado.
- `viewer`: somente leitura.

### 3.2 Enforcement
- Middleware FastAPI: extrai user/org da sessão, anexa ao `request.state`.
- Repository layer recebe `org_id` em todo método e filtra.
- Postgres RLS como **defense-in-depth** (não principal): mesmo se um query passar sem filtro, RLS bloqueia.

### 3.3 API key scopes (MVP)
- `ingest` (default): pode `POST /v1/traces`, `/v1/feedback`.
- `read`: pode `GET` em recursos do projeto.
- `admin` (perigoso, desabilitado por default): pode criar rubricas/experiments.

Scopes futuros: `manage_keys`, `export`.

## 4. Privacidade & dados sensíveis

### 4.1 Princípios
- **Schema sempre privacy-aware.** Mesmo com redaction off no MVP, o sistema **identifica** campos sensíveis.
- **Mínimo necessário.** Não ingerir o que não vai ser usado.
- **Right to erasure.** Suporte a `DELETE /v1/traces/{id}` e `DELETE /v1/users/me/data` (Futuro).
- **Sem PII em logs.** Logs do app contêm apenas IDs e metadata.

### 4.2 Redaction
- Lib: **Presidio** (Microsoft, OSS). Detectores default: EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN, IP, PERSON, LOCATION (ajustável).
- Modos:
  - `off` (default no MVP): nada é redatado.
  - `on_ingest`: redata `messages_in/out` antes de persistir. **Irreversível.**
  - `on_export`: persiste raw, redata só em export. (Recomendado para uso real.)
- Toggle em `Project.redaction_enabled` + `Project.redaction_mode`.
- Cliente também pode redatar antes (SDK `redact=...`) — recomendado quando há PII forte (saúde, financeiro).
- Eventos `pii_redacted` registrados nos spans para auditoria.

### 4.3 Retenção
- `Project.retention_days` (default 90, plan free: 30).
- Job diário deleta traces antigos.
- Audit log retido 365 dias.
- Backups retidos 7 dias (point-in-time Neon).

### 4.4 LGPD / GDPR
- **Base legal** (uso real, fora de portfólio): controlador é o cliente do EvalOps; EvalOps é operador. DPA template em [`docs/legal/`](legal/) — Futuro.
- **Portabilidade:** export do tenant em JSON.
- **Esquecimento:** `DELETE /v1/traces/{id}` por end-user (cliente fornece endpoint que repassa). Para apagar TODOS os traces de um end-user: `DELETE /v1/traces/by-user-ref/{hash}`.
- **Sub-processadores:** OpenAI/Gemini/Groq quando llm_judge é usado. Documentado.

## 5. Encryption

| Camada | Mecanismo |
|---|---|
| Em trânsito | TLS 1.3 (rejeita 1.2 e abaixo) |
| Em repouso (DB) | Postgres at-rest encryption (Neon default) |
| Em repouso (R2) | Server-side encryption AES-256 |
| Secrets | env vars; Vercel/Fly secrets manager |
| API keys | argon2id (não cifradas, hashed) |
| JWT signing | RS256 com chave RSA 2048 bits, rotação trimestral |

## 6. Rate limiting & abuse prevention

- **Por API key:** token bucket Redis; limite default 60/min, configurável.
- **Por IP:** 600/min em endpoints públicos; 10/min em endpoints de auth (magic-link).
- **Tamanho de request:** body máx 1 MB; batch máx 100 traces.
- **Idle key alert:** key sem uso por 90 dias gera notificação para owner.

## 7. Audit log

Tabela `audit_logs` registra:
- `api_key.created`, `api_key.revoked`
- `project.created`, `project.archived`, `project.settings_changed`
- `member.invited`, `member.removed`, `member.role_changed`
- `org.plan_changed`
- `trace.deleted` (LGPD)
- `rubric.published`
- `dataset.exported` (com filtros)

Visível em `/o/{org}/settings/audit` para owners/admins.

## 8. Secrets management

- Local dev: `.env` (no git ignore). `.env.example` documenta variáveis.
- Hosted: Vercel env vars (frontend) + Fly secrets (backend).
- Chaves de provider LLM são **server-side only**; nunca expostas ao frontend.

## 9. Vulnerability management

- `dependabot` no GitHub para alertas.
- `pip-audit` e `npm audit` em CI.
- `bandit` (Python static security) em CI.
- `gitleaks` para vazamento de secrets em PR.

## 10. Incident response (mínimo viável)

- Sentry → Slack/email do autor.
- Runbook em `docs/runbooks/` (Futuro):
  - "Ingestion endpoint 5xx em massa"
  - "Vazamento suspeito de API key"
  - "Quota mismatch"

## 11. Compliance posture (target)

- **MVP:** boas práticas, sem certificação.
- **6 meses:** SOC2 Type I — viável solo? **Não.** Focar em "SOC2-ready architecture": logs, audit, encryption, RLS, RBAC.
- **12 meses (se SaaS real):** SOC2 Type II + DPA + ISO 27001 são objetivo, fora do escopo de portfólio.

## 12. Termos da API e ToS

- Cliente concorda em **não** enviar dados sensíveis (saúde, infantis) sem ativar redaction.
- EvalOps reserva direito de inspecionar amostras agregadas para análise técnica em modo dev (claramente comunicado em ToS).
- Em modo portfolio: dados são tratados com mesmo rigor, mas o produto não é ofertado comercialmente — disclaimer no site.

## 13. Open questions

- **[Decisão pendente]** Tornar criptografia de prompts/respostas em DB **a critério do cliente** (BYOK)? Recomendação: Futuro; útil para enterprise.
- **[Decisão pendente]** SSO SAML/OIDC enterprise? Recomendação: Futuro (atende clientes corporativos).
- **[Decisão pendente]** PII detection client-side por default no SDK? Recomendação: **opt-in** no MVP — performance e falsos positivos.
