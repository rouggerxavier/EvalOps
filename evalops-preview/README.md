# EvalOps Studio — Preview interno (refatoração)

Preview frontend isolado da refatoração interna do EvalOps. **Não é o app real**,
não há backend conectado e nada é persistido. Serve como referência visual/UX
para a futura implementação no monorepo `rouggerxavier/EvalOps`.

## Como abrir

### Opção 1 (mais simples)
Abra `EvalOps Preview.html` no seu navegador.
É um arquivo HTML único e standalone — funciona offline, sem servidor, sem npm.

### Opção 2 (versão multi-arquivo, para inspecionar a estrutura)
Sirva a pasta `preview/` com qualquer servidor estático:

```bash
cd preview
python3 -m http.server 5173
# abra http://localhost:5173
```

Browsers bloqueiam fetch direto de arquivos locais via `file://`, então
o servidor estático é necessário **só** para a versão multi-arquivo.

## Navegação

O preview usa navegação por hash (`#/traces`, `#/traces/trc_8f4a92d1`,
`#/evaluations`, etc.) — clicar nos itens da sidebar funciona, e o botão
voltar do navegador funciona.

Atalhos de teclado (pressionar `G` e depois a letra):

| Combo | Tela |
|---|---|
| `G O` | Visão geral |
| `G T` | Traces |
| `G E` | Avaliações |
| `G X` | Experimentos |
| `G P` | Prompts |
| `G R` | Rubricas |
| `G D` | Datasets |
| `G K` | Chaves API |

## O que está aqui

```
preview/
├── index.html                  entry point
├── styles.css                  design system (tokens em :root)
├── data.jsx                    mocks + registry de endpoints reais
├── components.jsx              Badge, Card, Sparkline, AreaChart, Modal…
├── shell.jsx                   Sidebar, Topbar, router por hash
├── app.jsx                     wiring + atalhos
├── screens/
│   ├── overview.jsx
│   ├── traces.jsx              lista + detalhe (com painel RAG)
│   ├── evaluations.jsx
│   └── modules.jsx             Prompts, Rubricas, Datasets, Experimentos,
│                               Chaves API e Exports (placeholders premium)
├── README.md                   este arquivo
└── DESIGN_NOTES.md             direção visual, decisões, recomendações
```

Toda ação que dispararia uma chamada de backend abre um modal de **preview**
mostrando o endpoint real que seria acionado (método, path e descrição).
Nada é executado. O registry está em `data.jsx → ENDPOINTS`.

## Stack

- React 18 inline (UMD) + Babel standalone — zero build, zero npm
- CSS puro com tokens em `:root`
- Fontes: Inter + JetBrains Mono via Google Fonts
- Sem Tailwind, sem shadcn, sem Radix, sem MUI

## O que **não** está aqui

- Nenhum segredo/key/token real. As "chaves" exibidas em `/keys` são fictícias
  e mascaradas.
- Nenhum trace, prompt, dataset ou export de produção. Todo conteúdo é mock
  genérico baseado nos contratos da codebase, **anonimizado**.
- Telemetria, analytics, Sentry — nada disso. É um arquivo estático.
