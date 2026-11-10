# Roadmap da evolução — proposta

Data/base: 2026-11-09, main `545149b`. Não é lista de entregas existentes. Objetivo: preparar incrementos delegáveis, preservando núcleo atual. Sem prazo/calendário artificial; fase seguinte depende de aceite e valor observado. Segurança de cada fase é parte da entrega, não pacote final.

## Fases por dependência e valor

| Fase | Entrada/dependências | Entregáveis e áreas prováveis | Risco e conclusão objetiva | Validação prática |
|---|---|---|---|---|
| F0 — fundações mínimas | SPEC-001, 002 e subset 009 | Contratos/fixtures, ownership/principal/scopes, snapshot, ModelVersion, PredictionSet/TaskEvaluation/MetricFact; API models/schemas/services/migrations/tests | FK cruzada, compatibilidade; testes negativos e snapshot estável, legado intacto e Alembic head único | Reproduzir fixture sem mensagens/traces artificiais |
| F1 — vertical regressão humana e agente | F0, SPEC-003/004 mínima/007 descritiva/008 | Formulários tabulares, importação, métricas/resíduos, comparação, SDK e CLI JSON; web + sdk-python | Paridade/limites; E2E web e CLI verificam mesmos fatos; 10 mil linhas medidas | Engenheiro sem terminal e agente resolvem mesma tarefa |
| F2 — produto atual e AI-first utilizável | F1, SPEC-004 casos/investigações e 007 revisão | Revisar patch Grankasa local, explicitar synthetic/replay, curadoria com referência humana, retomar investigação, comparação de casos; MCP local opcional após CLI | Referência copiada virar verdade; manter draft/reviewed e revisão auditada | Falha observada vira caso revisado e regressão recuperável entre sessões |
| F3 — MVP classificação | F1 e contrato classificação SPEC-003 | Labels/probabilidades, matriz, F1/AUC/calibração e UI própria | Classe ausente, macro enviesada; fixtures e validade explícitas | Usuário identifica classe/segmento ruim que média esconde |
| F4 — runner de aplicações/agentes | F2, SPEC-005 e ledger/leases/políticas 009 | Primeiro importador de harness, depois runner externo registrado, cancelamento, fixtures e piloto com tools | Efeitos/gasto incerto; morte após gasto não repete chamada sem autorização; Postgres/Redis e egress testados | Bateria real A/B selada Grankasa ou outro consumidor; sem tráfego produtivo |
| F5 — DL por tarefa | F3; artefatos 006/009; F4 só para execução | Redes com mesmos contratos, curvas/recursos importados; escolher visão ou áudio com piloto | Métricas incompatíveis/media sensível; lineage e renderização segura | Comparar clássico/neural na mesma tarefa e evidência |
| F6 — avançado sob demanda | Resultados dos pilotos | Bootstrap pareado, clustering, forecasting, drift, importadores MLflow/W&B, MCP remote | Infra e estatística excessivas; experimento dedicado antes de cada expansão | Só entra se reduzir esforço/erro medido no benchmark |

F2/F3 podem avançar independentemente após F1, mas não abrir lanes sobre mesmos arquivos sem plano. MCP não bloqueia primeira integração AI-first. Infra gerenciada de execução, serving e treinamento permanecem fora do roadmap comprometido.

## Primeira entrega técnica exata (F0 + F1)

Caso: regressão escalar supervisionada **offline**. O usuário já produziu predições; EvalOps calcula qualidade dessas predições, não executa o algoritmo.

Inclui:

1. Dataset editável tabular e snapshot materializado de até 10 mil amostras/10 MiB, com sample_id, target numérico, unidade e segmentos.
2. Modelo/versão declarado com origem/proveniência; PredictionSet importado atomicamente por formulário web ou API.
3. TaskEvaluation com MAE/MSE/RMSE/R², cobertura, validade, resíduos e métricas por segmento.
4. Web para criar/importar/avaliar/inspecionar; nenhuma dependência de terminal ou IA. Resultados do agente aparecem na mesma lista.
5. API+SDK+CLI com principal/chave de projeto e scopes write/evaluate/read; uso revogável sem JWT pessoal.
6. Comparação descritiva pareada de duas avaliações no mesmo snapshot, delta/tolerância/cobertura e inconclusive quando insuficiente. Sem bootstrap ou claim de significância.
7. Evidência/hash/config/versão do avaliador persistidos; Idempotency-Key impede duplicar escrita; auditoria e isolamento em todos os filhos.

Exclui: executar modelo ou código, upload de pickle/pesos, runner, judge, MCP, treinamento, GPU, classificação, DL específico, registry completo e aprovação de deploy. Custo de inferência ausente permanece não medido; tempo do cálculo não vira latência do modelo.

Reprodutibilidade: mesma implementação/versionamento + predições + snapshot + configuração gera mesmas métricas dentro de tolerância 1e-12. Modelo externo declarado não pode ser regenerado pelo EvalOps nessa entrega. Identidade de output importado é verificável por hash; identidade do produtor pode ser apenas declarada.

## Pacotes de execução delegáveis

Cada pacote implementa somente sua fatia, reconfere main, preserva mudanças locais e entrega diff, comandos/resultados, contratos alterados e limites. Não executar funcionalidades durante esta rodada documental.

| Pacote | Ler antes | Saída e gate |
|---|---|---|
| P0 contratos/dados | models.py, schemas.py, ownership.py, migrations; SPEC-001/002/009 | schemas/tabelas e fixture, teste de snapshot/FK/projeto e upgrade preservando legado |
| P1 avaliação | registry/eval_service sem refatorá-los; SPEC-003 | serviço regressão/importação, teste numérico, missing e atomicidade |
| P2 programático | deps.py, SDK client/uploader; SPEC-004/009 | principal/scopes, idempotência, capabilities e CLI; teste de repetição/revogação/paridade |
| P3 comparação | experiment_service/routes_phase5 e SPEC-007 | kind/associação/compare offline; synthetic legado preservado; pares incompatíveis inconclusive |
| P4 web vertical | DESIGN.md, lib/api/actions/types, datasets/evaluations; SPEC-008 | fluxo humano completo e navegação; E2E 375/1280px, teclado e resultados API idênticos |
| P5 integração/valor | todos os aceites e auditoria | prova integrada, benchmark e relatório go/iterate/stop; zero mudança sem evidência de necessidade |

P0 deve integrar principal mínimo ou alinhar schema com P2 antes de serializar ownership; P1 depende P0; P2 depende contratos P0/P1; P3 depende P1; P4 depende endpoints P1/P2/P3. Não delegar arquivos compartilhados simultaneamente sem isolamento. Recomendado `execution-prompt-builder` após aceite do plano para gerar prompts finais; testes e review proporcionais na implementação.

## Verificação e rollback por fase

Inner loop: testes do contrato/serviço alterado. PR: regressão API/SDK, web tests/build se tocar web, migration PostgreSQL se schema; E2E vertical para F1. Runner exige integração Redis/PostgreSQL dedicada, falha/interrupção e egress. Não substituir esses gates por asserts sobre source. CI existente cobre migration, mas não runtime concorrente PostgreSQL nem E2E completo.

Rollback: desabilitar novas escritas/telas por deploy/configuração de release e manter dados novos; restaurar cliente anterior compatível. Nunca apagar snapshot/ledger como rollback. Reavaliar migration real e recuperação antes de cada fase; nenhuma migration foi criada neste plano.

## Medir valor sem antecipar vitória

Piloto com pelo menos dois engenheiros e um fluxo de agente, dataset público/sintético de regressão e três tarefas: achar segmento pior, comparar candidato e recuperar investigação/caso. Rodar mesmas tarefas com script próprio usando sklearn/JSON e com MLflow ou ferramenta que o piloto já utiliza. Mesmo dataset, protocolo, critério e tempo de preparação contabilizado.

Registrar tempo de setup/conclusão, intervenções humanas, chamadas/tokens/custo do agente, discrepâncias numéricas, decisões incorretas, recuperação após sessão nova e capacidade de auditar resultado. Critérios propostos de continuação: zero divergência numérica/tenant, todas evidências recuperáveis, >=80% tarefas concluídas sem correção do operador, e redução >=20% no tempo mediano de repetição frente ao baseline local após incluir setup. São metas de piloto, não resultados ou significância estatística. Se setup adicional não se amortizar, reduzir escopo ou integrar ferramenta existente. Publicar falhas e limitações, não apenas demo favorável.
