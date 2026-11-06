# EvalOps Studio · sistema

Escopo: interface autenticada do projeto. Landing, Login, Register, Docs, Changelog, Health e o seletor `/app` mantêm o visual existente.

## Rotas

- `/o/[org]/p/[project]` — Visão geral
- `/o/[org]/p/[project]/traces` — Traces
- `/o/[org]/p/[project]/traces/[trace]` — Detalhe do trace
- `/o/[org]/p/[project]/traces/compare` — Comparação
- `/o/[org]/p/[project]/evaluations` — Avaliações
- `/o/[org]/p/[project]/rubrics` — Rubricas
- `/o/[org]/p/[project]/prompts` — Prompts
- `/o/[org]/p/[project]/datasets` — Datasets
- `/o/[org]/p/[project]/experiments` — Experimentos
- `/o/[org]/p/[project]/keys` — Chaves de API
- `/o/[org]/p/[project]/exports` — Exports
- `/o/[org]/p/[project]/settings` — Ajustes

## Tokens

| Uso | Valor |
| --- | --- |
| Navegação, hover, ativo | `#14224F`, `#22316A`, `#2A3A72` |
| Fundo, painel, borda, cabeçalho de tabela | `#F3F5FA`, `#FFFFFF`, `#E1E5F0`, `#F7F8FC` |
| Borda de controle | `#D5DAE8` |
| Texto, texto secundário | `#121A36`, `#56607F` |
| Ação, hover | `#1D2F6F`, `#16265C` |
| Crítico, texto crítico, fundo crítico | `#C4261C`, `#A81F16`, `#FBE9E7` |
| Aprovado, alerta, dados | `#0F5C3C`, `#7E4B08`, `#8C9BCB` |

Schibsted Grotesk é a fonte da interface; JetBrains Mono identifica IDs e código. Corpo usa 13px, título principal 20px, painéis 13–14px. Painéis têm raio 8px e sem sombra. Controles têm 36px no desktop e 44px em telas de toque.

## Composição e comportamento

O shell usa navegação de 232px e barra superior de 56px. A navegação mostra projeto, contagem real de traces com erro/parciais e uso mensal de traces. Em telas estreitas (até 760px), a navegação abre como gaveta pelo botão de menu (`aria-expanded`), tem botão de fechar dentro do painel, prende o foco, fecha com Escape, com o fundo, ao trocar de rota ou ao alargar a janela, e devolve o foco ao botão. A barra superior empilha marca e menu, caminho (só no detalhe), busca, e ambiente, avisos e conta, sem sobreposição. A Visão geral mantém filtros de ambiente e período em 390px; tabelas longas rolam dentro dos painéis.

Todos os números vêm de endpoints existentes. Status de ingestão e veredito de avaliação aparecem separados. Estados sem dados usam “Sem dados”; erros e vazios mantêm mensagem e ação. Não são adicionados dados de exemplo ao produto.

## Limites da API

- A Visão geral não recebe período anterior. Não exibe variação `vs.`. Aprovação e tendência vêm dos relatórios por rubrica. A lista de atenção cobre as últimas 24h, todos os ambientes, e retorna no máximo 25 traces.
- A lista de traces filtra por período em dias inteiros UTC, tag `chave:valor`, usuário, modelo, nota abaixo de um valor, só reprovados, busca livre (`q`) e conversa. Scores e vereditos aparecem somente quando há execução de avaliação.
- A API não fornece score por versão de prompt nem estado pausado de avaliação. Esses campos mostram “Sem dados”.
- Datasets retornam até 100 itens por consulta e não expõem estado de build nem total exato acima desse limite.
- Experimentos retornam métricas por variante e as 20 execuções mais recentes por experimento, mas não p95. Resultados marcados `synthetic` exibem aviso.
- A listagem de chaves não inclui último uso. O segredo só aparece na resposta de criação; revogar e excluir pedem confirmação.
- Exports mostram status, linhas, tamanho, expiração e download autenticado. A listagem carrega 50 por página.
- Ajustes mostram uso e limites da organização. Gasto do juiz e total de membros não estão disponíveis; membros aparecem em consulta limitada a 50.

## Verificação

`apps/web` passa `npm run test` (184 testes), `npx tsc --noEmit` e `npm run build`. Todas as telas do projeto foram abertas em 1280 px e 375 px com a API local em SQLite: sem rolagem lateral da página, sem sobreposição na barra superior, menu do celular operado pelo teclado. Capturas de antes e depois em `docs/audits/img/redesign-*.jpg`.
