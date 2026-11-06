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

As etapas 1 a 3 da ordem sugerida foram corrigidas, e as promessas falsas da etapa 7 saíram da tela. Itens fechados:
S1, 1, 2, 3, 4, 5, 6, 8, 12, 13 e 21 a 28.

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

Validação: 411 testes API, 36 SDK, 156 web, typecheck e build. As regressões de produto e de P1 passaram em Postgres
16, e as telas foram conferidas no navegador, inclusive em 375 px.

Dois defeitos novos apareceram e foram corrigidos:

- `POST /v1/organizations` dava `ForeignKeyViolation` em Postgres, porque faltava `flush`. Em SQLite passava.
- Avaliações, Settings e Trace sanitizavam o erro duas vezes, então toda falha virava "Algo deu errado".

Limites:

- Na visão geral, Atenção e Cobertura ainda ignoram o ambiente.
- Com "qualquer env" em Traces e o chip em `dev`, o chip continua mostrando `dev` nessa visão.
- O item 10 só teve o texto da landing corrigido: avaliação automática continua inexistente.
- O passo a passo da landing (`EvalOpsFeatureStepper`) ainda fala em promover para produção.
- A Conversa mostra cada chamada separadamente: o histórico repetido fica recolhido, sem transcrição única. A
  linha do tempo da conversa inteira segue no item 9.
- O painel de run mostra a nota parcial ao lado de "sem veredito", avisando que ela cobre só parte dos avaliadores.
- O pacote `evalops-python` segue sem publicação, e o nome está livre no PyPI. Publicar é decisão pendente.

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
| 10 | **Sem avaliação automática.** Não há regra "avaliar X% do que chega". A landing promete "rubricas na ingestão". | `HowItWorksPipeline.tsx:24` | Leitura |
| 11 | **Filtros de trace insuficientes:** sem período, tag, `user_ref`, modelo, nota, reprovados ou flag. A busca da topbar só procura por nome. | `lib/api.ts:129` | Leitura |

## Quebrado ou sem saída

| # | Achado | Onde | Evidência |
|---|---|---|---|
| 12 | **Billing dá 404.** "Abrir Usage" aponta para `/o/{org}/usage`, que não existe. Uso e plano só aparecem escondidos em Exports. | `settings/page.tsx:44` | Provado |
| 13 | **Flag é só escrita.** Não há `GET` (405), a flag não aparece no trace e não há como ver o que foi marcado. | `routes_trace_actions.py`, `traces/[trace]/page.tsx:148` | Provado |
| 14 | **Resultado de experimento some.** Só aparece logo após rodar, via URL. Não há rota que liste runs nem tela de histórico. | `experiments/page.tsx:199` | Provado |
| 15 | **Celular sem navegação.** Em 375 px a sidebar fica `display: none`, não há menu, e breadcrumb, busca e chip se sobrepõem. | `AppShell`, `EvoTopbar` | Provado |
| 16 | **`prompt_version_ref` não é validado:** referência inexistente entra com 202 e distorce o uso do prompt. | `trace_ingest_service.py:170` | Provado |
| 17 | **Chave com `read` quase não lê.** Com a chave, dão 401: traces, prompts, rubricas, avaliações e feedback. Só relatório e lote aceitam. | `ownership.py:114` | Provado |
| 18 | **Feedback do usuário final não entra.** Exige login no painel e o SDK não tem método. Um "joinha" do WhatsApp não chega, e o feedback não entra em nenhuma métrica. | `routes_phase6.py` | Provado |
| 19 | **Prompts desligados da execução.** O SDK não busca prompt e a chave não lê. O agente continua com prompt no próprio código, então não há "promover variante". | `routes_phase6.py`, SDK | Provado |
| 20 | **Notificações só de avaliação.** Cota esgotada responde 402 sem aviso prévio nem sino, e a ingestão para em silêncio. | `eval_service.py:425` | Leitura |

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
