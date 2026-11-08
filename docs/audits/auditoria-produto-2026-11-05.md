# Auditoria de produto — EvalOps (2026-11-05)

Segunda auditoria, feita sobre `7f96da4` (branch `fix/p0-auditoria`). Complementa a
[auditoria de código](auditoria-codigo-2026-11-05.md): lá o foco era a nota estar certa; aqui é o produto
conseguir mostrá-la. O relatório original não alterou código; as correções estão em Status.

Método: cruzamento das 69 operações do OpenAPI com o cliente web, comparação do JSON real de 30 endpoints com
`lib/types.ts`, chamadas reais com chave de API e navegação no app com dados descartáveis.

Evidência: **provado** foi executado; **leitura** veio do código, sem execução.

## Veredito

O backend mede, mas o painel não deixa ver. A API já calcula nota por avaliador, motivo do juiz, lote e tendência
por versão, e nenhuma dessas informações aparece em tela. **A resposta do próprio agente também não aparece.**
Quem conectar a Grankasa hoje vê que uma nota existe e não consegue ler o que foi dito nem por que reprovou.

Os tipos do frontend estão bons: só `OverviewResponse.last_window` não existe na API. O problema é funcionalidade
não ligada, não contrato quebrado.

## Status

As etapas 1 a 4 foram corrigidas, e as promessas falsas da etapa 7 saíram da tela.
A etapa 6 tem amostragem, feedback por chave/SDK, busca de prompts e avisos de cota
integrados. Itens fechados no escopo descrito abaixo: S1, 1 a 17 e 19 a 28. O item
18 permanece parcial porque o feedback ainda não compõe métricas agregadas.

- **Instalação:** a documentação e a landing mandam instalar a partir do repositório e avisam sobre o pacote de
  terceiro. O quickstart usa `set_llm` e `set_trace`, e foi executado contra o SDK real com cliente simulado.
- **Trace:** novas abas Conversa e Avaliações, com mensagens, ferramentas, modelo, nota e motivo por avaliador. Flags
  aparecem no trace e na nova aba Marcados da lista. A coluna Modelo usa o último `llm_call`.
- **Uso:** YAML padrão válido; erro de rubrica com o campo a corrigir; campos sem efeito avisados na tela; chip de
  ambiente com "todos", seguido também por Avaliações; escopo `evaluate` na criação de chave; Plano e uso em Settings.
- **Promessas falsas:** login sem "manter conectado", SSO, Termos e Política; cadastro sem aceite de documentos que
  não existem nem promessa de e-mails; painel lateral com resumo do produto no lugar do depoimento e sem limites de
  plano inventados. A landing mostra só o SDK Python, com `set_llm` e `set_trace`, e "Como funciona" descreve
  avaliação sob demanda, quality gate e export JSONL. A aba Pausadas saiu de Avaliações. O quickstart usa
  `evk_prod_` com `environment="prod"`, que é o prefixo gerado para chave de `prod`, o padrão da tela de chaves.

- **Celular (item 15):** fechado no shell novo do redesign (`OpsShellFrame`, `Sidebar`, `EvoTopbar`). Até 760 px
  a navegação abre como gaveta pelo botão de menu (`aria-expanded`), com botão de fechar dentro do painel, foco
  preso, Esc, fechamento ao trocar de rota ou ao alargar a janela e foco de volta no botão. A barra superior empilha
  marca e menu, caminho (só no detalhe), busca, e ambiente, avisos e conta, sem sobreposição. Todas as telas do
  projeto foram abertas em 375 px e 1280 px sem rolagem lateral da página. Antes e depois em
  [`img/`](img/redesign-antes-visao-geral-375.jpg).

Validação da rodada inicial: 411 testes API, 36 SDK, 156 web, typecheck e build. As regressões de produto e de P1 passaram em Postgres
16, e as telas foram conferidas no navegador, inclusive em 375 px.

Dois defeitos novos apareceram e foram corrigidos:

- `POST /v1/organizations` dava `ForeignKeyViolation` em Postgres, porque faltava `flush`. Em SQLite passava.
- Avaliações, Settings e Trace sanitizavam o erro duas vezes, então toda falha virava "Algo deu errado".

Limites atuais:

- Na visão geral, Atenção e Cobertura ainda ignoram o ambiente.
- Com "qualquer env" em Traces e o chip em `dev`, o chip continua mostrando `dev` nessa visão.
- Tags sem `:` são descartadas no filtro sem aviso.
- A navegação por conversa mostra os 50 turnos mais recentes, sem paginação no detalhe. O título Conversa aparece no agrupamento e na aba.
- O painel de run mostra nota parcial ao lado de "sem veredito", avisando que ela cobre apenas os avaliadores que mediram.
- A interface do lote não explica o reenvio de traces parciais ou com erro.
- Há horários sem fuso nas respostas da API, afetando a apresentação relativa.
- O stepper da landing fala em checklist antes de promover para produção; o produto apoia essa decisão, sem promover variantes automaticamente.
- O feedback ainda não é agregado às métricas, e os avisos não cobrem orçamento do juiz por fonte incompleta de gasto.
- O pacote `evalops-python` segue sem publicação. A instalação pelo repositório continua válida; publicar é decisão pendente.

### Atualização em 2026-11-08: feedback e prompts no SDK

O [PR #32](https://github.com/rouggerxavier/EvalOps/pull/32) foi integrado após
revisão independente de autorização e CI verde. O SDK agora oferece
`Client.feedback(client_trace_id, ...)`, `Client.get_prompt(prompt_id, version=...)`
e `current_client_trace_id()`. Chaves somente `read` não escrevem feedback;
chaves `ingest` alcançam apenas o próprio projeto. O caminho JWT anterior foi
preservado. IDs iguais em projetos distintos não misturam feedback.

O feedback deve ser enviado após a ingestão do trace. `flush()` aguarda a fila,
mas não garante que a API aceitou o trace; o cliente pode receber 404. O POST não
é repetido automaticamente após uma falha ambígua, evitando duplicação. A
auditoria identifica o tipo de ator e o projeto da chave, sem identificar a
chave individual. As métricas ainda não agregam esse feedback.

Validação local: 50 testes API; 80 testes SDK em Python 3.12. A CI passou nas
quatro versões suportadas do Python, além de API, web e migração em PostgreSQL 16.
A revisão independente verificou também credenciais expiradas/revogadas,
precedência de headers, isolamento e propagação assíncrona do contexto do SDK.

### Atualização em 2026-11-08: redesign e avisos de cota

Os PRs [#31](https://github.com/rouggerxavier/EvalOps/pull/31) e
[#33](https://github.com/rouggerxavier/EvalOps/pull/33) foram integrados depois de
revisões independentes, CI individual e CI da árvore combinada verdes. A árvore
final coincidiu com a composição validada.

O redesign preserva a operação em 1280/375 px e navegação móvel por teclado.
A revisão encontrou e corrigiu duas regressões: perda de vereditos/erros do
histórico e classificação limitada às 100 avaliações mais recentes do projeto.
Agora nota e veredito vêm da mesma execução, e o filtro é aplicado antes da
paginação. A paginação GET preserva os filtros. Evidências e limites em
[redesign-qa-2026-11-08.md](redesign-qa-2026-11-08.md).

Os avisos de cota são transacionais, aparecem ao cruzar 80% e não se repetem ao
marcar como lidos. Os projetos ativos da organização recebem cópias independentes;
projetos criados depois aguardam o próximo cruzamento. A correção também impede
perda de incrementos concorrentes em PostgreSQL: a regressão `70 + 4 × 5` passou
a registrar 90. Com quatro incrementos de 10, três são aceitos, um recebe 402 e o
contador termina em 100. O orçamento do juiz segue fora dos avisos por falta de
uma fonte completa de gasto. O flush seletivo utilizado é suportado na versão
instalada do SQLAlchemy, com aviso de depreciação para manutenção futura.

### Atualização em 2026-11-08: avaliação por amostragem

O [PR #34](https://github.com/rouggerxavier/EvalOps/pull/34) integrou a regra
"avaliar X% do que chega", com rubrica e versão fixa por projeto. Ela começa
desativada e vale para todos os ambientes. A seleção é persistida junto do trace;
falha de fila não desfaz a ingestão aceita. O painel mostra configuração,
resultados e ações necessárias.

A revisão inicial encontrou recuperação automática capaz de repetir uma chamada
paga após crash. A correção foi revisada novamente: o início da tentativa fica
durável antes do provider, e a recuperação transforma execução interrompida em
resultado incerto, sem nova chamada automática. Retry manual exige confirmação de
possível cobrança e é auditado. Gasto anterior ao crash pode ficar sem
contabilização; não há promessa de execução única no provider.

Passaram 202 testes web, typecheck/build, 86 testes API afetados e 14 testes em
Postgres 16. A migração upgrade/downgrade/upgrade e a limpeza de advisory locks
foram verificadas. O fluxo com API, Redis e worker reais isolados concluiu uma
avaliação heurística, sem LLM pago. Configuração, confirmação e aviso de cota
foram conferidos em 1280/375 px. Revisões independentes de backend e UI e CI final
verde precederam o merge.

Operação, migração e limites estão em
[avaliacao-amostragem.md](../ops/avaliacao-amostragem.md). Comandos, cenários e
capturas estão em [amostragem-qa-2026-11-08.md](amostragem-qa-2026-11-08.md).

## Segurança

| # | Achado | Onde | Evidência |
|---|---|---|---|
| S1 | **A documentação manda instalar pacote de terceiro.** `pip install evalops` existe no PyPI e pertence a outro autor (The-Swarm-Corporation). Nosso pacote é `evalops-python` e não está publicado (404). Quem seguir a página executa código alheio na máquina que guarda a chave. | `app/docs/page.tsx:120` | Provado |

## Bloqueia medir pelo painel

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 1 | **A resposta do agente não aparece em lugar nenhum.** Nenhuma tela renderiza `messages_in`, `messages_out`, `input`, `output`, `model` ou `provider` de span, embora a API devolva. O trace só mostra a barra do waterfall. Vale para traces sem spans de RAG. | `traces/[trace]/page.tsx` | Provado |
| 2 | **O motivo da nota não aparece.** `reasoning`, `scores` e `run_metadata` só existem em `lib/types.ts`. Avaliar um trace dá só "criado com sucesso", e o detalhe não tem aba de avaliações. `GET /v1/evaluations/{id}` e `GET /v1/traces/{id}/evaluations` ficam sem uso. | `traces/[trace]/page.tsx:29` | Provado |
| 3 | **"Nova rubrica" em Avaliações vem com YAML que sempre falha:** sem `name` e `description`, com `type: builtin`, que não existe. | `evaluations/evaluations-modals.tsx:204` | Provado |
| 4 | **Erro de rubrica não diz o que corrigir.** A API responde só `invalid_rubric`, então a validação nova do P1 rejeita sem explicar. `ignored_fields` também não chega à tela. | `api/routes_rubrics.py` | Provado |
| 5 | **Filtro de ambiente quebrado.** O chip mostra `prod` por padrão e lista todos os ambientes. Depois de escolher `dev`, não há como voltar a "todos": o chip não tem essa opção e "qualquer env" é ignorado, porque o cookie vence o parâmetro vazio. Avaliações ignora o chip (3 runs com o chip em `dev`). | `lib/active-env.ts:22`, `EvoTopbar.tsx:17` | Provado |
| 6 | **Coluna Modelo sempre vazia.** Ela lê `metadata.model`, mas o modelo fica no span, e o item da lista não traz o campo. O detalhe mostra "sem modelo" em trace com preço calculado. | `lib/trace-display.ts:53` | Provado |
| 7 | **Lote e relatório só existem na API.** Na tela, avalia-se um trace por vez. Não há tendência de score (o gráfico do overview é só custo), nem comparação entre versões de rubrica, embora `/rubrics/{id}/report` já calcule. | `routes_evaluations.py:131,196` | Provado |
| 8 | **Chave `evaluate` não pode ser criada na tela:** os checkboxes só oferecem `ingest` e `read`. | `keys/page.tsx:468` | Leitura |
| 9 | **Conversa invisível.** `conversation_id` existe na API, sem filtro nem linha do tempo. Trace é um turno, então uma conversa da Grankasa fica espalhada na lista. | `traces/page.tsx` | Leitura |
| 10 | **Fechado.** O #34 adiciona configuração de amostragem em Ajustes, com percentual, rubrica e versão fixa, desativada por padrão. Seleção durável, worker e recuperação preservam o trace aceito. Resultado incerto exige confirmação de possível nova cobrança antes de retry. | `routes_sampling.py`, Settings, worker | Corrigido, revisado e testado |
| 11 | **Filtros de trace insuficientes:** sem período, tag, `user_ref`, modelo, nota, reprovados ou flag. A busca da topbar só procura por nome. | `lib/api.ts:129` | Leitura |

## Quebrado ou sem saída

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 12 | **Billing dá 404.** "Abrir Usage" aponta para `/o/{org}/usage`, que não existe. Uso e plano só aparecem escondidos em Exports. | `settings/page.tsx:44` | Provado |
| 13 | **Flag é só escrita.** Não há `GET` (405), a flag não aparece no trace e não há como ver o que foi marcado. | `routes_trace_actions.py`, `traces/[trace]/page.tsx:148` | Provado |
| 14 | **Resultado de experimento some.** Só aparece logo após rodar, via URL. Não há rota que liste runs nem tela de histórico. | `experiments/page.tsx:199` | Provado |
| 15 | **Fechado.** **Celular sem navegação.** Em 375 px a sidebar fica `display: none`, não há menu, e breadcrumb, busca e chip se sobrepõem. | `AppShell`, `EvoTopbar` | Provado |
| 16 | **Fechado.** **`prompt_version_ref` não é validado:** referência inexistente entra com 202 e distorce o uso do prompt. | `trace_ingest_service.py:170` | Provado |
| 17 | **Fechado.** **Chave com `read` quase não lê.** Com a chave, dão 401: traces, prompts, rubricas, avaliações e feedback. Só relatório e lote aceitam. | `ownership.py:114` | Provado |
| 18 | **Parcial.** Feedback por chave `ingest` e pelo SDK foi integrado no #32, com resolução de `client_trace_id` dentro do projeto e auditoria. O envio não exige login no painel. A incorporação do feedback às métricas permanece pendente. | `routes_phase6.py`, SDK | Corrigido e testado; métricas pendentes |
| 19 | **Fechado no escopo de busca.** A chave `read` lê prompts após #30; `Client.get_prompt(prompt_id, version=...)`, integrado no #32, retorna a versão atual ou fixa com seu template. Não foi adicionada promoção automática de variantes. | `routes_phase5.py`, SDK | Corrigido e testado |
| 20 | **Fechado no escopo de cotas mensais.** O #33 avisa ao atingir 80% dos limites de traces, avaliações, exports, spans e tokens. O sino mostra uma cópia por projeto ativo, com leitura independente. O orçamento do juiz ainda não gera aviso porque a fonte de gasto é incompleta. | `usage_service.py`, sino existente | Corrigido e testado |

## Promessas falsas

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 21 | **Fechado.** "Manter conectado por 30 dias": o campo `remember` é ignorado. | `login/page.tsx:70`, `lib/auth-actions.ts` | Leitura |
| 22 | **Fechado.** "SSO disponível no plano Team": não há SSO nem plano Team. | `login/page.tsx:82` | Leitura |
| 23 | **Fechado.** Termos e Política apontam para `#`, e esses documentos não existem. Risco jurídico para quem guarda conversa de cliente. | `login/page.tsx:81` | Leitura |
| 24 | **Fechado.** Depoimento fictício com nome e cargo ("Maya Halil"), citando detecção de drift, que não existe. | `AuthSidePanel.tsx:201` | Leitura |
| 25 | **Fechado.** Aba "TypeScript" no SDK: só existe SDK Python. | `SDKShowcase.tsx:174` | Leitura |
| 26 | **Fechado.** Aba "Pausadas" diz que avaliações são pausadas automaticamente: nada faz isso. | `evaluations/page.tsx:473` | Leitura |
| 27 | **Fechado.** Quickstart não usa `set_llm` nem `set_trace` e não obtém resposta avaliável; a chave do exemplo (`evk_live_`) não segue o prefixo real (`evk_dev_`). | `docs/page.tsx:120` | Leitura |
| 28 | **Fechado.** "Promova a melhor variante" e experimentos "entre modelos": não há promoção, e experimentos são simulados. | `HowItWorksPipeline.tsx` | Leitura |

## Funcionalidade ausente

| Área | Falta | Evidência |
|---|---|---|
| Conta | Recuperar e trocar senha, editar perfil, excluir conta. **Sem recuperação, senha esquecida exige SQL.** | Provado (sem rota) |
| Organização | Convidar membro, remover, papéis. Criar e trocar de organização tem API (`/v1/organizations`), sem tela. | Provado (sem rota) |
| Exclusão | Rubrica, prompt, dataset, item de dataset, experimento, projeto e organização não têm `DELETE`. `DELETE /v1/traces/{id}` existe, sem botão. | Provado |
| Edição | Rubrica sem reverter versão; item de dataset e experimento não editam. | Provado (sem rota) |
| Dataset | "Adicionar este trace ao dataset" a partir do trace, e correção humana virando exemplo. | Leitura |
| Retenção | Traces guardam conversa para sempre: não há prazo nem limpeza. `maintenance.run_all` segue sem agendamento. | Leitura |
| Regressão | Portão de CI (PR #19 em rascunho) e comparação pareada de duas versões do agente. | Leitura |

## Acabamento

- Idioma misturado: "Members", "General", "Billing", "in 3 hours" (`lib/format.ts:55` fixa `en-US`), erros de login
  em inglês e menu sem acento ("Avaliacoes", "Operacao").
- Telas exibem rota da API como subtítulo, por exemplo `POST /v1/projects`.
- "agora atrás" em runs recentes (`evaluations/page.tsx:463`).
- Título "Abrindo seu workspace ? EvalOps Studio", arquivo com BOM (`app/app/page.tsx`) e `h? 2 min` no painel de login.
- Changelog parado na 0.7.0 de abril; sidebar diz `v0.7` e o mock da landing, `v1.0`.
- `AreaChart` gera id com `Math.random`, causando hydration mismatch (provado).
- Código morto: `RubricDrawer`, `QuickstartCard`, `UserMenu`, `LogoLoop`, 6 componentes de `components/ui`, 9 exports
  de `lib/rag.ts`.
- Rotas sem cliente web: `GET /v1/me`, `GET /v1/prompts/{id}`, `GET /v1/rubrics/{id}`,
  `GET /v1/rubrics/{id}/versions/{n}`.
- Prompts faz uma chamada de uso por prompt ao abrir a tela (`prompts/page.tsx:155`).

## Ordem sugerida

1. **Corrigir a instalação (S1):** ajustar a documentação antes de qualquer divulgação. Publicar `evalops-python`,
   ou instruir a instalação pelo repositório.
2. **Ver o que foi medido (1, 2, 6, 13):** conversa, modelo e tools no trace; aba de avaliações com nota, motivo e
   flags por avaliador.
3. **Destravar o uso (3, 4, 5, 8, 12):** YAML válido, erro de rubrica com a causa, filtro de ambiente, escopo
   `evaluate` e página de uso.
4. **Medir em volume (7, 9, 11, 14):** lote e relatório na tela, tendência por versão, conversa e filtros.
5. **Ligar a Grankasa:** adaptador e primeira bateria sintética.
6. **Fechar o ciclo (10, 18, 19):** avaliação automática por amostragem e feedback pelo SDK.
7. **Antes de ter outros usuários:** promessas falsas (21 a 28), recuperação de senha, retenção, exclusão, convites
   com papéis e navegação no celular.

## Não verificado

- Fluxos completos de Datasets, Prompts, Exports, Compare e Reexecutar no navegador: só leitura.
- Telas em Postgres: a navegação usou SQLite. O "in 3 hours" pode vir de data sem fuso nesse banco.
- Acessibilidade e desempenho com volume real.
- Pacote `evalops` do PyPI: só os metadados foram consultados. Ele não foi instalado nem analisado.
