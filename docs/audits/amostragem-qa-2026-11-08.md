# Avaliação por amostragem — validação em 2026-11-08

A implementação usa a main com os PRs #31, #32 e #33 integrados. A regra começa
desativada e permite escolher percentual, rubrica e versão fixa em Ajustes.

## Comportamento e regressões

O backend foi revisado independentemente no SHA
`0bbe3253ed145c985bead37751c929fafac54a7e`. A revisão inicial reproduziu duas
chamadas externas após crash antes do commit, apesar de existir somente um run
persistido. A correção grava o início da tentativa antes do provider; a entrega
seguinte passa a `uncertain` e não chama o provider novamente. Retry manual exige
confirmação de possível cobrança, com aviso e auditoria.

A revisão independente conferiu SQLite, Postgres 16, migration upgrade/downgrade,
pool de uma conexão, concorrência entre pools, rollback e liberação de advisory
locks após Exception/BaseException. Uma falha injetada no unlock invalidou a
conexão, e o checkout seguinte não herdou locks. Não houve chamada a LLM pago.

A interface foi concluída depois desse gate. O POST nativo dos formulários
reaproveita validação e autorização das ações existentes, verifica origem,
limita o formulário a 16 KiB e usa redirecionamento 303. Foram testados origem
estrangeira/ausente, ação inválida, redirecionamento externo, erro inesperado,
formulário malformado e corpo transmitido acima do limite.

A lista prioriza resultados incertos e bloqueados, para que uma tentativa antiga
que exige confirmação não suma atrás dos registros concluídos mais recentes.
Uma regressão cria 21 resultados recentes e mantém o resultado incerto antigo
visível na consulta limitada a 20.

## Gates locais finais

- 86 testes API afetados passaram, com um skip de concorrência específico de SQLite.
- 14 testes de amostragem passaram em Postgres 16, no banco exclusivo da lane.
- 202 testes web passaram, incluindo 12 testes novos de formulário, ações e POST nativo.
- Typecheck e build passaram.
- Detector Impeccable dos componentes alterados: zero achados.

Os gates de CI e a revisão independente do delta de UI ainda precisam ser
concluídos antes do merge. O gate anterior do backend não aprova automaticamente
o novo endpoint web nem as alterações de apresentação.

## Fluxo real isolado

API, build web e worker foram iniciados com SQLite descartável e um Redis 7
exclusivo, publicado apenas em loopback. Nenhum Redis compartilhado foi usado.
A conta e os dados são sintéticos, criados apenas nesse ambiente.

O fluxo percorreu a gravação da regra no painel, a ingestão de um trace, o
marcador durável, o despacho pelo Redis real e a avaliação por um worker arq real.
A rubrica usa apenas `length_bounds`; o job terminou com um run associado. Um
limite de cinco traces na organização de QA permitiu conferir o aviso de 80%
após o quarto trace. O sino mostrou o aviso.

Em 1280 e 375 px, o painel salvou a configuração e a consulta seguinte preservou
100%, a rubrica e sua versão. Não houve overflow da página nem erro JavaScript.
Uma fixture separada representa resultado incerto: sem marcar a confirmação, o
browser bloqueou o envio e o estado continuou incerto. Após a confirmação, o
POST foi aceito e o estado saiu de `uncertain`.

O redirecionamento do Server Action no cliente apresentou a mesma espera
intermitente observada anteriormente na base do redesign: a API salvava, mas a
navegação não concluía. Os formulários desta funcionalidade usam POST nativo,
validado no navegador com redirecionamento 303. Não foi feita alteração global
do router.

## Capturas

Dados sintéticos do ambiente descartável, renderizados pelo build da aplicação:

- [Formulário em 1280 px](img/amostragem-2026-11-08-form-1280.png)
- [Formulário em 375 px](img/amostragem-2026-11-08-form-375.png)
- [Confirmação em 1280 px](img/amostragem-2026-11-08-retry-1280.png)
- [Confirmação em 375 px](img/amostragem-2026-11-08-retry-375.png)

As capturas de confirmação representam uma fixture de estado incerto; não são
comprovação de uma cobrança real. A interrupção depois do provider foi testada
com stub controlado e revisada separadamente.

## Limites

Gasto anterior a um crash pode ficar sem contabilização. Uma nova tentativa
manual pode cobrar novamente; não há promessa de execução única no provider.
SQLite coordena apenas o mesmo processo; múltiplos workers devem usar Postgres.
A lista do painel mostra até 20 registros, com prioridade explícita. Não foram
verificados LLM externo, carga de produção, Firefox, WebKit ou dispositivo físico.
