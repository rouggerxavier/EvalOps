# 24. Codebase Audit & Repository Structure

Data da auditoria: 2026-04-29

## Resumo executivo

O repositório deixou de ser apenas um projeto "spec-driven" e hoje ja possui:

- backend funcional em `apps/api`
- frontend funcional em `apps/web`
- SDK Python em `packages/sdk-python`
- suite de testes do backend cobrindo fases 1 a 4

O maior problema de organizacao nao esta na arquitetura do produto, e sim na higiene
do workspace: artefatos locais de ambiente e dependencias instaladas foram misturados
com o codigo da API, o README raiz ficou desatualizado e a navegacao entre docs e
implementacao nao reflete mais o estado real do projeto.

## O que existe hoje

### Codigo de produto

- `apps/api/app`
  - API FastAPI
  - modelos SQLAlchemy
  - schemas Pydantic
  - rotas de identidade, tracing, analytics, rubrics e evaluations
- `apps/api/tests`
  - testes de fases 1 a 4
- `apps/web/app`
  - dashboard Next.js App Router
  - overview do projeto
  - listagem de traces
  - detalhe de trace
- `apps/web/components`
  - `Sidebar.tsx`
- `apps/web/lib`
  - cliente HTTP do dashboard
  - tipos TypeScript compartilhados no app
- `packages/sdk-python`
  - cliente/SDK Python para ingestao

### Documentacao

- `docs/00` a `docs/23`
  - produto, arquitetura, dominio, API, operacao e ADRs
- `docs/examples`
  - payloads e exemplos sinteticos

## Principais problemas encontrados

### 1. Dependencias instaladas dentro de `apps/api`

O diretorio da API contem bibliotecas e metadados de ambiente como:

- `httpx`, `jinja2`, `jsonschema`, `yaml`, `anyio`, `certifi`, `jwt`
- varios `*.dist-info`
- `bin/`
- `.venv/`
- caches como `__pycache__` e `.pytest_cache`

Impacto:

- dificulta navegar no backend
- polui `git status`
- aumenta o risco de commit acidental de ambiente local
- mistura codigo autoral com codigo de terceiros

Direcao recomendada:

- manter codigo versionado apenas em `apps/api/app`, `apps/api/tests`, `apps/api/scripts`
- manter ambiente Python fora do tree da API, de preferencia na raiz do repo com `.venv/`
- usar `pip install -e apps/api[dev]` ou fluxo equivalente em vez de instalar dependencias dentro da pasta do app

### 2. README raiz desatualizado

O `README.md` ainda afirma que nao existe implementacao, mas o projeto ja tem:

- endpoints reais
- frontend real
- testes reais
- SDK Python

Impacto:

- gera leitura errada para quem entra no repo
- dificulta onboarding
- enfraquece a documentacao como fonte de verdade

### 3. Frontend e backend evoluiram, mas a cola entre eles ainda nao esta uniforme

Exemplo claro observado na auditoria:

- o overview do projeto resolve `org_slug + project_slug -> project_id`
- a pagina de traces estava tentando consultar a API usando o `slug` como se fosse `project_id`

Isso indica que a integracao web/api ainda precisa de uma pequena camada de consistencia
compartilhada.

### 4. Ausencia de guia de estrutura do repositorio

A documentacao esta muito boa no nivel de produto e arquitetura, mas faltava um documento
curto dizendo:

- onde mora o frontend
- onde mora o backend
- onde mora o SDK
- quais pastas sao codigo fonte vs ambiente local

### 5. Cobertura assimetrica

O backend possui testes automatizados bem melhores que o frontend.

Impacto:

- regressao de navegacao ou integracao do dashboard pode passar despercebida
- bugs simples de contrato front/api tendem a aparecer tarde

## Estrutura recomendada para navegar no repo

```text
EvalOps/
  apps/
    api/
      app/          # backend FastAPI
      tests/        # testes backend
      scripts/      # utilitarios de desenvolvimento
      README.md
      pyproject.toml
    web/
      app/          # rotas e telas Next.js
      components/   # componentes de UI
      lib/          # cliente API e tipos do dashboard
      package.json
  packages/
    sdk-python/     # SDK Python oficial
  docs/             # specs, ADRs e exemplos
  README.md         # entrada principal do repo
```

## Acoes aplicadas nesta rodada

- ajuste de `.gitignore` para blindar o root de `apps/api` contra artefatos locais
- correcao da pagina de listagem de traces para usar `project_id` real
- atualizacao do README raiz para refletir o estado atual
- inclusao deste documento de auditoria/estrutura

## Proximos passos recomendados

1. Extrair o ambiente Python local de dentro de `apps/api` e recriar a instalacao em uma `.venv` na raiz.
2. Adicionar um `README.md` curto em `apps/web` explicando variaveis de ambiente e rotas principais.
3. Criar testes do frontend para navegacao basica e contratos do cliente HTTP.
4. Definir se a documentacao continuara descrevendo alvo futuro, estado atual, ou ambos explicitamente.
