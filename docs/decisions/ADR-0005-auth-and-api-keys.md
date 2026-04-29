# ADR-0005 — Auth & API Keys

- **Status:** Accepted
- **Data:** 2026-04-29

## Contexto

Duas audiências de credenciais:
1. **Usuários humanos** acessando o dashboard.
2. **Apps clientes** instrumentando com SDK / curl.

Cada uma exige modelo distinto.

## Decisões para usuários (dashboard)

### Provider

- **Auth.js v5 (NextAuth)** com:
  - **Email magic link** (default — sem senha; menos liability, fricção razoável).
  - **GitHub OAuth** (público-alvo é dev — login rápido).

> Considerados e rejeitados: Clerk ($25/user/mo em escala; vendor lock-in para portfólio); auth próprio (time-suck).

### Session

- Cookie `__Secure-evalops.session`, HttpOnly, Secure, SameSite=Lax.
- Sessão persistida server-side em DB (`sessions` table do Auth.js).
- Inatividade: 30 dias.
- JWT NÃO é exposto ao cliente; o cookie é referência opaca.

### Frontend → API

- Server Components do Next.js leem sessão e chamam API com `Authorization: Bearer <jwt>` (JWT curto, 15 min, gerado por BFF; rotacionado).
- Client Components fazem fetch via Server Actions encapsuladas — JWT nunca chega ao browser.

## Decisões para apps clientes (API keys)

### Formato

- `evk_{env}_{36 chars base62}`.
- Exemplo: `evk_live_a1b2c3d4e5f6g7h8i9j0klmnopqrstuvwxyz`.
- Exibida ao usuário **uma única vez** após criação.

### Armazenamento

- **Hash argon2id**, parâmetros: `m=19MiB, t=2, p=1`. (Conformidade OWASP 2025.)
- Armazenamos **prefix** (primeiros 14 chars) em claro para identificação na UI.
- Lookup: `WHERE prefix = ?` → verify hash. Limita escopo de busca.

### Rate limiting

- Token bucket por API key, persistido em Redis.
- Default 60 req/min, configurável por key.
- Resposta 429 com `Retry-After`.

### Scopes (MVP)

- `ingest`: pode `POST /v1/traces` e `/v1/feedback`.
- `read`: pode `GET` em recursos do projeto.
- `admin`: pode criar rubricas/experiments (opt-in, default off).

> Scopes futuros: `manage_keys`, `export`, `delete_traces` (LGPD).

### Revogação

- `revoked_at = now()`. Cache invalidado via Redis pub/sub (`evalops:keys:revoked`).
- Revogação tem efeito em < 60s (NFR-13).

### Last used

- `last_used_at` atualizado **ao máximo 1x por minuto** (debounce em Redis) para evitar write amplification em ingestion alta.

## Modelo de roles na org (MVP)

Roles flat (sem RBAC granular):

| Role | Permissões |
|---|---|
| `owner` | Tudo na org, incluindo billing e remoção de membros |
| `admin` | Tudo exceto billing |
| `member` | Ler/escrever projetos onde for adicionado |
| `viewer` | Read-only |

> RBAC granular (recursos × ações × roles customizados) é Fase 3.

## Multi-tenancy enforcement

- **Layer 1 (principal):** Repository layer recebe `org_id` em todo método e filtra. Tests cobrem isso.
- **Layer 2 (defense-in-depth):** Postgres Row-Level Security (RLS) em todas as tabelas com `organization_id`. Policy `current_setting('app.org_id')::text = organization_id`. App seta `SET LOCAL app.org_id = ...` no início de cada transaction.
- **Layer 3:** API key resolve `project_id` → `org_id`; queries cross-org retornam 404 (não 403, para não vazar existência).

## Audit log

Tabela `audit_logs` registra:
- `api_key.created`, `api_key.revoked`, `api_key.used_first_time`.
- `member.invited`, `member.removed`, `member.role_changed`.
- `org.plan_changed`.
- `trace.deleted` (compliance).

## Decisões rejeitadas

| Opção | Razão |
|---|---|
| Senhas para humanos | Liability sem ganho; magic link cobre |
| API keys em JWT | Não é o uso; JWTs expiram e exigem rotação ativa pelo cliente |
| MFA no MVP | Out of scope; adicionar em Fase 2 via Auth.js TOTP |
| OAuth 2.0 client credentials para clientes server-to-server | Overkill; API key cobre 100% |
| Per-resource ACL fino | RBAC granular é Fase 3 |

## Consequências

**Positivas:**
- Magic link reduz fricção e elimina senha-related liability.
- API keys com argon2 + scopes + revocation cobrem padrão da indústria.
- 3-camada de tenancy enforcement permite dormir tranquilo.

**Negativas:**
- Sem MFA no MVP é gap conhecido (mitigação: pequeno público no MVP).
- Magic link depende de provedor de email (Resend) — falha do provedor bloqueia signup.
- RBAC flat limita uso enterprise (mitigação: target MVP é dev solo / time pequeno).

## Quando reavaliar

- Pedido de cliente para SSO (SAML/OIDC) → Fase 3.
- Incidente de key vazada → adicionar prefix scoping mais estrito + alertas.
- Crescimento em equipes grandes → priorizar RBAC granular.
