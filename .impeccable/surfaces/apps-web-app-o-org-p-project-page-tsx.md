---
version: 1
slug: "apps-web-app-o-org-p-project-page-tsx"
primary_target: "apps/web/app/o/[org]/p/[project]/page.tsx"
related_targets: []
---

# App do projeto EvalOps

Escopo: shell e telas do projeto. Modo Operate. Público: engenheiros de IA e pessoas não técnicas que só querem saber se a IA faz o que deveria.
Tarefa: abrir o projeto e saber o que precisa de atenção, chegando ao trace responsável em um passo.
Direção: Painel de operação, aprovada pelo usuário no piloto do canvas. Substitui "Prova corrigida" nas telas do sistema; as páginas públicas ainda usam a direção anterior. Entrega em canvas primeiro; código só depois da aprovação.

## Direction contract

THESIS: O EvalOps é um sistema de trabalho, não um documento. Cada tela mostra estado, números e próxima ação com a densidade e a previsibilidade de um painel de operação.

OWN-WORLD: Menu azul-marinho #14224F com seleção #2A3A72, fundo #F3F5FA, painéis brancos com borda #E1E5F0 e raio de 8px, tinta #121A36, apoio #56607F, ação #1D2F6F. Vermelho #C4261C só para atenção, verde #0F5C3C para aprovado, âmbar #7E4B08 para alerta. Schibsted Grotesk em 13px com números tabulares, JetBrains Mono só para IDs e código.

STORY: A pessoa lê um resumo em português, vê os números do período e a lista do mais grave ao menos grave, abre o trace e encontra o motivo ligado à evidência.

FIRST VIEWPORT: Menu escuro à esquerda, barra superior com caminho, busca, ambiente, avisos e conta. Título de 20px, resumo em linguagem simples, faixa de números, painel de atenção e tabela.

FORM: Painel de operação com menu lateral, painéis e tabelas densas. seed: none (unavailable)

Assinatura: resumo em linguagem simples no topo, para quem não é técnico, sobre uma interface densa para quem é. Raises: situação sempre com ícone e texto, controles de 36px e 44px em toque, tabela é o padrão para listas, trecho reprovado destacado na resposta.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
