# SPEC-008 — Experiência humana e interface gráfica

Status: **proposta, não implementada**. Data: 2026-11-09. Base: `545149b`.


## Problema, objetivo e reuso

Web atual oferece operações LLM, mas datasets e avaliações assumem texto. Atender usuário humano sem IA/terminal e permitir analisar atividade de agentes. Reusar shell, CSS, tokens, componentes de tabela/formulário, Server Actions, feedback e DESIGN.md; sem redesign ou chat novo. Esta SPEC descreve evolução, não telas já disponíveis.

## Navegação e telas propostas

| Área existente | Evolução e fonte de dados |
|---|---|
| Overview | Separar saúde de produção atual e avaliações offline; card leva a resultados, sem média entre tarefas incompatíveis. |
| Datasets | Seletor textual/tabular, editor/importação JSON, preview de erros, referências e revisão; lista de snapshots com digest/data/n. Não renderizar números como mensagens. |
| Avaliações | Abas Traces/Tarefas; criar avaliação escolhe snapshot, modelo/versão e predições; resultado mostra status, cobertura, métrica/unidade/validade e erros por categoria. |
| Modelos (novo item) | Catálogo leve de ModelVersion, fonte/digest/proveniência e links aos resultados. Sem botão treinar ou implantar. |
| Experimentos | Preservar aviso synthetic; comparação nova mostra baseline, delta, tolerância, cobertura, inconclusive, pares e revisão. |
| Traces | Preservar spans e feedback; distinguir “Repetir chamada LLM” de “Executar cenário” quando runner existir; ocultar ação indisponível via capabilities. |
| Investigações (subárea Avaliações) | Hipóteses/resumo/evidências/execuções/próximos passos, revisões concorrentes e autor humano/serviço; continuidade entre sessões. |
| Settings/Keys | Principal/scopes/limites, orçamento, políticas e plano para execução cara; segredo uma vez, revogar/rotacionar. |

Rotas futuras sob `/o/[org]/p/[project]`: `/models`, `/evaluations/tasks/[id]`, `/datasets/[id]/snapshots/[snapshot]`, `/experiments/[id]/runs/[run]`, `/evaluations/investigations/[id]`. Listas existentes continuam com URLs/filtros funcionais; links no response da API resolvem o ID, sem expor storage path.

## Visualizações por tarefa

Regressão: MAE/RMSE/R² com unidade e n, resíduos vs predição, histograma e maiores erros; tabela acessível acompanha gráfico. Classificação: matriz com eixos verdadeiro/predito, support, precision/recall/F1 e gráficos de curva/calibração somente quando válidos. DL: curvas por split e recursos medidos. Agentes: timeline de tools/spans, estado/fixtures, conclusão da tarefa e custo conhecido/desconhecido. Não representar RMSE como barra de aprovação 0–1.

## Fluxo vertical sem terminal

1. Criar dataset regression, inserir/importar casos JSON e revisar preview.
2. Criar snapshot; cadastrar modelo/versão declarada e importar prediction rows pelo formulário/arquivo local.
3. Solicitar avaliação limitada e abrir resultado persistido.
4. Inspecionar resíduos, referência e caso; comparar segunda versão.
5. Copiar link/ID para agente; abrir resultado criado pelo agente na mesma lista.

Não exigir código, SDK, IA ou upload de modelo. Download de template JSON e validação local ajudam, mas validação autoritativa ocorre na API. Formulários mantêm valores após erro, apontam linha/campo e não aceitam importação parcial silenciosa.

## Contratos e equivalência

Consumir endpoints SPEC-002/004/007/009; web nunca mantém banco paralelo ou calcula decisões autoritativas. Cliente recebe capability e schema de tarefa; falha HTTP preserva erro acionável. Revisão de caso usa PATCH `/v1/datasets/{d}/cases/{item}` com revision/If-Match; edição conflitante retorna 409. Aprovação humana exige ator humano e política admin; service principal pode sugerir, não impersonar.

| Operação | Humano | Agente |
|---|---|---|
| Importar, snapshot, avaliar e comparar | Formulário web | HTTP/SDK/CLI |
| Explorar evidência e métricas | Gráfico/tabela e links | JSON paginado e artifact refs |
| Criar caso/investigação | Editor | HTTP tipado |
| Aprovar decisão crítica | UI autenticada e auditada | Solicita revisão, sem se passar por humano |

DTOs de comparação usam `view=task_v1` (SPEC-007); UI nunca converte ausência de passed para reprovação. Exibir pass=“Aprovado pela política”, fail=“Reprovado pela política”, review=“Revisão necessária”, inconclusive=“Inconclusivo” com razões/cobertura. Estado não terminal null é “Aguardando decisão”; resultados antigos mostram passed histórico e marca “Legado”. Séries preservam lacunas por state/reason e matrizes preservam orientação de eixos (SPEC-002). Capabilities, listas e downloads respeitam labels de origem; filtro visual de ambiente não é fronteira de autorização. Aceite negativo: comparison inconclusive não ganha badge fail; snapshot prod-only não aparece nem por contagem/erro para credencial dev.

## Não funcionais e aceite

Preservar pt-BR, teclado, foco, labels, contraste e status sem depender só de cor. Touch targets/tokens conforme DESIGN. Gráficos com tabelas equivalentes; suporte 375px e desktop 1280px sem scroll horizontal da página (tabelas podem rolar internamente). Empty/missing/error/inconclusive distintos; zero medido aparece como zero. Nenhum gráfico com dados fictícios em produção.

## Dependências e compatibilidade

SPEC-002/003/004 mínima para vertical; 007 para comparação; 006 para visualizações DL; 009 para auth. Não alterar DESIGN.md nesta etapa. Rotas antigas e atalhos permanecem; migrar copy de replay explicitamente ao implementar. Bibliotecas novas de gráfico só após testar reutilização/CSS/SVG básico e acessibilidade; não prescrever pacote agora.

## Riscos, testes e plano

Risco de criar painel exclusivo de agentes ou cockpit genérico incompreensível. Aceite E2E: usuário sem terminal completa vertical; agente cria avaliação e usuário encontra mesmo ID/métricas; viewer não escreve, estado inconclusive aparece com motivo. Testar erro de upload, falta de rótulo, IDs longos, teclado, mobile e gráfico/tabela equivalentes. Screenshot e runtime QA necessários na implementação; inspeção de source não basta.

1. Formulários dataset/predições e resultados de regressão.
2. Catálogo leve e comparação.
3. Investigação/revisão humana.
4. Classificação e DL conforme avaliadores liberados.
