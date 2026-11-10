# Política e identidade de runner

Fundação de controle F4. Esta entrega configura policy e registro; dispatch permanece indisponível. Nenhum processo, lease ou reserva é criado por registrar um runner ou salvar uma policy enabled.

## Administração humana

A web oferece Avaliações > Evidências de execução > Gerenciar runners. Um owner registra nome, ambientes e adapters/versionados, cria credencial temporária e pode revogar a credencial exibida ou desabilitar todo o runner. A chave aparece apenas na resposta de criação; a UI mantém o valor somente no estado da página. Não há armazenamento no navegador ou URL. Desabilitar o runner invalida suas credenciais imediatamente.

Policy tem revisão e hash. GET `/v1/projects/{project_id}/execution-policy` retorna versão 0 desabilitada sem gravar quando não há policy. PUT no mesmo caminho exige owner, If-Match e Idempotency-Key; cria revisão imutável. Edição com versão antiga recebe 409; repetição do mesmo recibo devolve a mesma revisão. Campos v1: enabled, environments, allowed_adapters (id/version), max_cost_per_run_usd, monthly_budget_usd, max_parallel e effects_policy=fixtures_only. Valores monetários são Decimal; teto por execução não supera mensal. Zero é permitido para fixtures sem custo.

Registro: POST/GET `/v1/projects/{project_id}/runners` (owner). Desabilitar: POST `/v1/runners/{runner_id}/disable` com Idempotency-Key. Nome, owner responsável e capabilities são imutáveis; para alterar capacidades, registre outro runner e desabilite o anterior. Ausência ou perda do papel owner do responsável invalida a identidade, mesmo que outro owner continue no projeto.

Credencial: POST `/v1/runners/{runner_id}/credentials` com expires_at ISO/timezone, no futuro e até 90 dias. Retorna segredo uma vez com Cache-Control=no-store e grava somente hash. Não há retry automático: perda da resposta exige desabilitar o runner se não for possível revogar a credencial perdida por ID. Revogação por ID: POST `/v1/runners/{runner_id}/credentials/{credential_id}/revoke`. Runner/credencial devem corresponder; owner não cria nova credencial para registro cujo responsável perdeu o papel.

## Identidade de runtime

Credencial de runner usa `X-EvalOps-Runner-Key`, tabela própria e nunca recebe read/write/evaluate da API normal. GET `/v1/runners/{id}/capabilities` retorna somente o registro autorizado, sem segredos. Credencial expirada/revogada, runner desabilitado, owner sem papel ou runner incorreto retorna 401. Enviar a chave em X-EvalOps-Key não concede acesso à API.

SDK:

```python
import os
from evalops import RunnerClient

runner = RunnerClient(runner_key=os.environ["EVALOPS_RUNNER_KEY"], api_url=os.environ["EVALOPS_API_URL"])
capabilities = runner.capabilities("RUNNER_ID")
```

CLI:

```bash
evalops runner-capabilities RUNNER_ID --json
```

Esse comando exige EVALOPS_RUNNER_KEY; não usa EVALOPS_API_KEY como fallback. Dispatch_available e managed_sandbox continuam false. RunnerClient compartilha o transporte HTTP, mas não herda métodos de leitura geral do Client.

## Evidência e rollback

Migration 0017 aditiva: revisões de policy, registro e credenciais hash. Guards impedem alterações de policy/capabilities seladas. Downgrade exige tabelas vazias; rollback de código mantém registros e credenciais. Não apagar evidência para liberar migration.

Testes cobrem CAS, histórico imutável, roles/IDOR, segredo ausente em consultas, revogação, expiração, owner removido e chave usada em runner errado/API comum. Corrida de policy é verificada em PostgreSQL dedicado. E2E humano em 375/1280 px cobre criação/revogação da chave e disable. Nenhum teste realiza chamada paga ou usa credenciais de produção.

Próxima entrega precisa de ledger, plano selado, leases, revalidação da credencial original e fontes, cancelamento/ack e retenção de gasto incerto. Registro sozinho não comprova isolamento do processo cliente.
