# P7 — 9 Módulos Parity Plan

> Plano de execução por fases. Cada fase é uma página do app interno
> reaproximada do design `evalops-preview/` do ZIP `segunda refatoração
> interna EvalOps.zip`, **sem virar placeholder**, **sem perder
> funcionalidade**, **mantendo o background atual** da `.evo-shell`.

Branch: `refactor/frontend`
Repo: `/home/rouggerxavier/dev/evalops`
Handoff-pai: `docs/plans/cockpit-refactor-handoff-2026-05-20.md`
Design-fonte: `segunda refatoração interna EvalOps.zip` (raiz)
  - `preview/screens/{overview,traces,evaluations,modules}.jsx`
  - `preview/components.jsx` (`PageHeader`, `Card`, `Badge`, `Icon`,
    `summary-card`, `endpoint-list`, table `.t`, `PreviewPill`)
  - `preview/styles.css` (tokens visuais — referência, **não importar**)
  - `evalops-preview/DESIGN_NOTES.md` (raciocínio)

---

## Premissas fixas (não violar em nenhuma fase)

1. **Não virar placeholder.** Páginas reais já têm conteúdo funcional;
   refator é visual + estrutura, não substituição. NÃO renderizar
   banner "módulo preservado, fora do redesign principal" do ZIP.
2. **Não perder nada.** Toda funcionalidade hoje visível precisa
   continuar visível e funcional: formulários, ações de criar/
   versionar/revogar, listagens, drawers, diffs, banners de segurança,
   estados de erro/loading.
3. **Conectar backend real.** Nenhum dado mock. Métrica/badge/contagem
   só aparece se vier do payload existente. Sem inventar `avgScore`,
   `expires_at`, `errors_7d`, etc.
4. **Background fica.** `.evo-shell` atual (grid, vignettes radiais,
   cobalto `#4F8CFF`, oklch tokens) é o que o user gostou — manter.
   NÃO copiar background do preview se diferir.
5. **Tokens só dentro de `.evo-shell`.** Sem `:root`, sem vazamento
   pra landing/login/docs/changelog.
6. **Botões planejados** = `disabled data-status="planned"`, nunca
   modal de preview (cockpit Potemkin).
7. **Bem parecido, não idêntico.** Adaptar onde o ZIP tem dado mock
   que não existe no backend.

---

## Fases

Convenção: cada fase = 1 commit `feat(web): P7.x <módulo> parity`,
1 arquivo de teste novo `apps/web/tests/<módulo>-p7.test.mjs` (ou
extensão do `*-premium.test.mjs` existente). Doc handoff
(`cockpit-refactor-handoff-2026-05-20.md`) atualizada ao fim com hash
do commit e seção "P7.x — Files Changed".

Status legend: ⬜ pendente · 🟨 em andamento · ✅ landed

### P7.1 — Prompts ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/prompts/page.tsx`,
  possíveis splits em `apps/web/components/`.
- Referência: `evalops-preview/preview/screens/modules.jsx` (caso
  `moduleId === "prompts"`) + tabela `.t` + `endpoint-list` +
  `summary-card`.
- Conteúdo a preservar:
  - `createPromptAction`, `createPromptVersionAction` (formulários).
  - `DiffView` (diff por linha com `+`/`−`).
  - Listagem `getPrompts` + `getPromptVersions`.
  - Estados de erro/loading.
- Cockpit a aplicar:
  - `evo-page-header__eyebrow` "Operação · Prompts" (já presente
    do P5 — preservar).
  - Summary row real (ex.: total de prompts, total de versões,
    última atualização). Só dado do payload.
  - Wrap em `.evo-card` (header + body + footer).
  - Tabela com classes premium (linhas hoverable, mono col pra
    `version_hash`, badges para status).
  - Coluna lateral "Endpoints ativos" listando rotas reais
    (`POST /v1/prompts`, `POST /v1/prompts/{id}/versions`) como
    referência visual (somente leitura, não clicável → não vira
    modal).
- Testes a adicionar:
  - Server contract preservado (mesmas chamadas a `lib/api`).
  - Form fields permanecem (`name="slug"`, `name="template"`, etc).
  - `DiffView` renderiza ambos os casos (primeira versão + diff).
  - Nenhum `AttentionStrip`/dado inventado.

### P7.2 — Rubricas ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/rubrics/page.tsx`.
- Referência: ZIP `modules.jsx` (`moduleId === "rubrics"`).
- Preservar: criar rubrica (YAML), nova versão, listagem
  `getRubrics`/`getRubricVersions`.
- Cockpit: eyebrow já presente; summary (total rubrics, total
  versions, tipos), tabela premium, coluna endpoints reais.

### P7.3 — Datasets ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/datasets/page.tsx`,
  `datasets/loading.tsx`, `datasets/error.tsx`.
- Referência: ZIP `modules.jsx` (`moduleId === "datasets"`).
- Preservar: `createDatasetAction`, `addDatasetItemAction`,
  `buildDatasetFromTracesAction`, listagem com size.
- Cockpit: summary (total datasets, total itens, fontes), tabela
  premium, endpoints reais.

### P7.4 — Experiments ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/experiments/page.tsx`.
- Referência: ZIP `modules.jsx` (`moduleId === "experiments"`).
- Preservar: `createExperimentAction`, `runExperimentAction`,
  listagem com estado da run, link pra detalhe.
- Cockpit: summary (total, em execução, concluídos), badges de
  estado (`rodando`/`concluído`/`falhou`), tabela premium.

### P7.5 — Chaves API ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/keys/page.tsx`,
  `keys/loading.tsx`, `keys/error.tsx`.
- Referência: ZIP `modules.jsx` (`moduleId === "keys"`) + banner
  segurança já presente do P5.
- Preservar: `createApiKeyAction`, `revokeApiKeyAction`, máscara
  de prefix, flash do segredo cru via `consumeApiKeyFlash`, banner
  de política.
- Cockpit: summary (ativas, revogadas), tabela com badge
  `ativa`/`revogada`, ação revogar inline (form com confirm),
  endpoints reais. **NÃO** adicionar dot de atenção sem
  `expires_at` no tipo `ApiKey` (gap registrado no handoff-pai).

### P7.6 — Exports ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/exports/page.tsx`,
  `exports/loading.tsx`, `exports/error.tsx`.
- Referência: ZIP `modules.jsx` (`moduleId === "exports"`).
- Preservar: `createExportAction`, painel de usage/quota
  (Fix-7B.7), download via rota autenticada (`exports/[id]/
  download`), sanitização de erros.
- Cockpit: summary (total jobs, prontos, pendentes), tabela com
  badge `pronto`/`expirado`/`processando`, card "Limites do export"
  (já existem dados reais no ZIP — replicar texto se aplicável).

### P7.7 — Traces (re-tune) ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/traces/page.tsx`,
  `traces/[trace]/page.tsx`, `TracesFilterBar.tsx`.
- Referência: ZIP `preview/screens/traces.jsx`.
- Preservar: server contract, cursor guard, RAG segment (UI-RAG-1),
  auto-refresh client (`Phase 7E`), waterfall, raw metadata,
  feedback form.
- Re-tune: aproximar do ZIP em hierarquia visual sem trocar
  layout (NÃO usar tabs no detail). Ajustes pontuais em headers,
  badges, spacing.

### P7.8 — Overview (re-tune) ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/page.tsx`.
- Referência: ZIP `preview/screens/overview.jsx`.
- Preservar: signals reais, sem `avgScore` inventado, sem
  AttentionStrip sem sinal real.
- Re-tune: hero/header + summary cards mais próximos do ZIP.

### P7.9 — Evaluations (re-tune) ⬜

- Arquivos: `apps/web/app/o/[org]/p/[project]/evaluations/page.tsx`,
  `RubricDrawer.tsx`, `DistBars.tsx`.
- Referência: ZIP `preview/screens/evaluations.jsx`.
- Preservar: drawer rubrica, dist bars com dados reais,
  `triggerEvaluationAction`.
- Re-tune: layout secondary cards, badges, ações.

---

## Workflow por fase

1. `git status` limpo na branch `refactor/frontend`.
2. Ler arquivo alvo + ZIP de referência (`/tmp/evo-design/` já
   tem `modules.jsx`; extrair os demais quando precisar).
3. Implementar mantendo todo conteúdo funcional.
4. Adicionar/estender teste em `apps/web/tests/`.
5. `cd apps/web && npm test` (esperar 100% pass).
6. `npx tsc --noEmit -p apps/web/tsconfig.json` (esperar limpo).
7. Hit a página via curl `http://localhost:3000/...` pra verificar
   HMR sem erros novos. Conferir `/tmp/evalops-logs/web.log`.
8. Commit `feat(web): P7.x <módulo> parity`.
9. Atualizar este arquivo: `⬜` → `✅` + hash do commit + bullet
   "Files Changed".
10. Atualizar `cockpit-refactor-handoff-2026-05-20.md` (seção
    P7.x — Files Changed + Validation).

---

## Pendências fora deste plano (referência)

- Backend signals (`expires_at` em ApiKey, `/overview/counts`) —
  destrava dot Keys e sidebar Traces count. Trackado no
  handoff-pai §Pending Work · Gaps condicionais.
- Cleanup de inline alerts (`qp.created`/`qp.error`) agora que
  toast cobre o caso — pós-P7 ou fase própria.
- Auditoria visual Chromium+Firefox + contraste ≥4.5:1 —
  handoff-pai §Resume Prompt opção (c).

---

## Resume Prompt (a ser usado quando retomar)

```text
Continuando P7 (9-módulos parity) no EvalOps.

Repo: /home/rouggerxavier/dev/evalops
Branch: refactor/frontend
Plano: docs/plans/p7-nine-modules-parity-plan.md
Handoff-pai: docs/plans/cockpit-refactor-handoff-2026-05-20.md
Design-fonte: segunda refatoração interna EvalOps.zip

Faça apenas a fase indicada pelo usuário. Não avance pra próxima
sem pedido. Ao terminar: atualizar checkbox + hash no plano e
seção "Files Changed" no handoff-pai.

Premissas duras: não virar placeholder · não perder
funcionalidade · background atual fica · sem dado inventado ·
tokens só em .evo-shell · botões planejados = disabled
data-status="planned".
```
