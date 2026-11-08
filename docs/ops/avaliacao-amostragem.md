# Avaliação automática por amostragem

Em **Ajustes → Avaliação automática**, escolha o percentual de novos traces, a
rubrica e uma versão fixa existente. A configuração começa desativada; 0% não
seleciona traces e 100% seleciona todos. A regra vale para todos os ambientes do
projeto. Alterar ou desativar a regra não modifica os registros já selecionados.

A seleção usa uma decisão estável por projeto e ID do trace. Reenviar o mesmo
`client_trace_id` não cria outra seleção. A seleção é confirmada na mesma
transação da ingestão; indisponibilidade da fila não desfaz um trace aceito.

## Operação

O worker arq existente procura registros pendentes a cada minuto, em lotes de até
100. Uma entrega enfileirada cujo resultado não chegou pode ser reenfileirada
após cinco minutos. A execução verifica cotas e orçamento do juiz pelos serviços
existentes; isso não equivale a reservar previamente toda despesa externa.

Se uma tentativa começou e o processo caiu antes de salvar o resultado, seu
estado passa a **Resultado incerto**. A recuperação automática não chama o juiz
novamente. O painel mantém esses registros antigos visíveis antes dos resultados
concluídos e exige confirmação explícita para uma nova tentativa.

Uma chamada anterior pode ter sido cobrada pelo provider sem custo ou resultado
salvo no banco. Repetir manualmente pode cobrar novamente. Não há garantia de
execução única no provider; a confirmação registra que o usuário reconheceu esse
risco. Uma falha comprovada na fila antes da execução continua tendo recuperação
automática.

O painel mostra até 20 registros, priorizando resultados incertos e bloqueios.
Após solicitar nova tentativa, atualize a página para acompanhar a execução.
Uma avaliação manual já existente para o mesmo trace, rubrica e versão é
preservada; a seleção automática é marcada como não executada nesse caso.

## API

Todas as rotas pertencem ao projeto informado no caminho:

| Método e caminho | Escopo de chave | Comportamento |
|---|---|---|
| `GET /v1/projects/{id}/evaluation-sampling` | `read` | Configuração atual; retorna desativada quando ainda não há configuração. |
| `PUT /v1/projects/{id}/evaluation-sampling` | `evaluate` | Salva percentual, rubrica e versão. |
| `GET /v1/projects/{id}/evaluation-sampling/jobs` | `read` | Até 100 registros; aceita `limit`, com prioridade para resultados incertos e bloqueios. |
| `POST /v1/projects/{id}/evaluation-sampling/jobs/{trace_id}/retry` | `evaluate` | Solicita outra tentativa de um registro que admite retry. |

JWT mantém a autorização de membro da organização. Uma chave não alcança outro
projeto. Rubrica e versão são validadas no projeto antes de salvar.

Exemplo de configuração:

```json
{
  "enabled": true,
  "percentage": 10,
  "rubric_id": "id-da-rubrica-do-projeto",
  "rubric_version": 1
}
```

Para repetir um resultado incerto, envie o corpo abaixo somente depois de
reconhecer a possível nova cobrança. Sem confirmação, a API responde 409 com
`sampling_retry_requires_cost_confirmation` e o aviso. O campo `retry_warning`
no registro também apresenta essa explicação.

```json
{"confirm_possible_charge": true}
```

O painel usa POST nativo com verificação de origem e formulário limitado a 16 KiB.
A validação e a autorização continuam nas ações e na API; IDs ocultos de projeto
não substituem a resolução autenticada do contexto.

## Implantação e bancos

Aplique a migration **0012** antes de iniciar a versão nova da API e do worker.
O comando do worker permanece `python -m arq app.workers.settings.WorkerSettings`.
Configure `REDIS_URL` explicitamente; sua ausência usa o padrão da biblioteca e
pode alcançar um Redis compartilhado.

PostgreSQL usa advisory lock por seleção, com uma conexão fixada durante a
tentativa e liberação antes de devolvê-la ao pool. SQLite protege apenas workers
no mesmo processo; use PostgreSQL para múltiplos processos. Em SQLite local,
concorrência de worker igual a 1 evita entregas ocupadas que aguardariam a janela
de recuperação.

O downgrade remove configurações e marcadores de amostragem. Pare o worker antes
de executá-lo e preserve os dados necessários. Ele não desfaz cobranças externas.
