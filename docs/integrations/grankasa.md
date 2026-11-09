# Grankasa e EvalOps: primeira bateria sintética

A Grankasa possui um harness opt-in em `backend/evals/evalops_bridge`, integrado
pelo [PR #254](https://github.com/rouggerxavier/Grankasa/pull/254). Ele decora as
portas de modelo e ferramentas da Mariana Minimal, envia os turnos como traces
e confere ingestão, avaliações e relatório. Não liga captura produtiva nem muda
agente, prompt, worker, sender ou frontend da Grankasa.

**Somente dados sintéticos.** Mensagens, argumentos, fatos e exceções são
registrados integralmente. Este adaptador não oferece mascaramento para
conversas reais. Nenhuma mensagem é enviada ao WhatsApp.

## Executar

Use um projeto isolado do EvalOps, API e worker com a mesma `DATABASE_URL` e
`REDIS_URL` explícitas. Não aponte a bateria para o Redis compartilhado por outro
projeto. O script usa a API HTTP; Postgres e Redis não são simulados na prova
registrada abaixo.

Configure no ambiente:

| Variável | Uso |
|---|---|
| `EVALOPS_API_URL` | URL da API terminando em `/v1` |
| `EVALOPS_API_KEY` | Chave `dev`, escopo `ingest`, do projeto de teste |
| `EVALOPS_TOKEN` | JWT de um membro autorizado a criar rubrica e ler resultados |
| `EVALOPS_PROJECT_ID` | ID do mesmo projeto da chave |
| `GRANKASA_CHECKOUT` | Checkout da Grankasa contendo o bridge integrado |

No ambiente virtual da Grankasa:

```bash
cd "$GRANKASA_CHECKOUT/backend"
python -m pip install -r requirements.txt
python -m pip install -r evals/evalops_bridge/requirements.txt
python -m evals.evalops_bridge --project-id "$EVALOPS_PROJECT_ID" --rounds 2
```

O SDK é uma dependência opcional do harness, fixada no commit
`1abbeb5c6f8de0e264e19277d59b5d80eff94d68` do EvalOps. Não depende de publicação
no PyPI e não entra nas dependências do produto Grankasa. O
[runbook do consumidor](https://github.com/rouggerxavier/Grankasa/blob/aa004e9f62d20906e674f1db4e68bc82245494f3/docs/agent/evals/evalops-bridge.md)
explica o override explícito para desenvolver com outro checkout do SDK.

O único modo é `scripted`: catálogo e falas são locais. `--mode live` é recusado
antes de inicializar o SDK. O script aceita de 1 a 83 rodadas, gera lote e
conversas com UUID, captura `client_trace_id` e sela cenários/rubrica por hash.
Depois de drenar a fila, confirma pela API cada ID, projeto, ambiente e matriz;
`shutdown=True` sozinho não comprova que a ingestão aceitou os dados.

A rubrica existente só é reutilizada se tiver a mesma fonte. O enqueue fixa os
IDs e a versão. Erro técnico, ausência, duplicidade, timeout, matriz diferente
ou relatório divergente fazem o CLI sair com erro. Uma rubrica de mesmo slug e
conteúdo diferente exige revisão ou outro projeto; não é sobrescrita em silêncio.

## Resultado da primeira conexão

Foram executadas duas baterias no head Grankasa
`900fbeed4cf136daf35a8460712bf2402fadf440`, contra API e SDK EvalOps
`1abbeb5c6f8de0e264e19277d59b5d80eff94d68`. A integração entrou na main da
Grankasa em `aa004e9f62d20906e674f1db4e68bc82245494f3`, com revisão independente,
Quality Gate completo e Cloudflare verdes. A mudança de base posterior era
apenas frontend, sem sobreposição; a árvore do merge coincidiu com a composição
local verificada.

| Por bateria | Resultado |
|---|---:|
| Cenários × variantes × rodadas | 3 × 2 × 2 |
| Traces aceitos / avaliações concluídas | 12 / 12 |
| Respostas corretas aprovadas | 6 |
| Respostas inventadas reprovadas | 6 |
| Erros técnicos / sem veredito | 0 / 0 |
| Spans chain / llm_call / tool | 12 / 24 / 12 |

As duas baterias reutilizaram a mesma rubrica, versão 1. Os 24 traces, IDs,
spans, vereditos e relatórios foram conferidos por leitura independente da API.
O ambiente usou Postgres 16, migrations até `0012_evaluation_sampling`, Redis
exclusivo, API HTTP e worker arq reais. Conexões externas do harness foram
bloqueadas; um teste negativo confirmou o bloqueio antes da conexão. Não houve
provider de modelo ou sender real. O gasto externo da bateria foi R$ 0.

O [artefato de QA](../audits/grankasa-qa-2026-11-09.json) contém os commits,
hashes, matrizes e respostas agregadas da API, sem credenciais ou conversa real.
Os serviços, containers e credenciais efêmeros foram encerrados/removidos depois
da prova.

## O que o resultado permite afirmar

O caminho adaptador → SDK → ingestão → persistência → fila → avaliador → relatório
funcionou para os casos definidos. A taxa de aprovação esperada é 50% porque
metade das falas foi deliberadamente inventada; isso representa sucesso desta
bateria discriminativa, não uma nota da Mariana.

A regex separa os seis textos sintéticos de preço. Ela não prova fundamentação
factual geral: um preço de outro item do catálogo pode passar, e formatos não
previstos podem reprovar mesmo com o valor correto. Não mede conversa real,
modelo, entrega no canal ou qualidade de produção. Uma futura avaliação com
modelo real exige cenários próprios, comparação pareada e teto de custo antes
da execução.

Tokens e custo do modelo não foram medidos. `cost_source=unknown` nos traces é
preservado; a ausência de chamadas externas demonstra gasto zero, não uma
medição financeira fornecida pelo modelo.
