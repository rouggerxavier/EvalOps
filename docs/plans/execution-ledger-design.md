# Planos e ledger de execução — decisões locais

A entrega seguinte mantém importações externas separadas de execução controlada. Plano sela manifest, runner e revisão de policy; fila posterior sela identidade/credencial original do solicitante. Nenhum processo executa no API.

Budget de organização é explícito, owner-only e revisionado; ausência é disabled. Policy existente continua limitando projeto. Reserva exige ambos os tetos, versões e adapters/ambientes compatíveis. Atualizações de budget usam CAS; limite não pode cair abaixo de compromisso contabilizado. Desabilitar budget bloqueia novos trabalhos sem apagar reservas.

Ledger é append-only com Decimal USD, versão de medição e chaves únicas por execução/evento. Contas de quota guardam unidades inteiras de 10^-8 USD para não depender da aproximação NUMERIC do SQLite. Conversão usa Decimal validado com oito casas; não há cálculo monetário em float. Reserva altera contas de organização/projeto e ledger na mesma transação. Limite monetário v1 de 1 bilhão USD cabe em int64 nessa unidade.

Lock order: criação de execução usa lock de projeto do serviço de recibos, depois organização. Settlement segue a mesma ordem. Alterar budget de organização trava apenas organização e não adquire locks de outros projetos. Conta mensal registra período da reserva; settlement usa esse período, inclusive se o mês mudar. Slots ativos são consultados nas reservas de todos os períodos, para não reiniciar paralelismo na virada do mês.

max_parallel conta slots admitidos, incluindo queued, running e tentativa incerta não isolada. Manifest declara paralelismo interno e reserva esse peso, limitado pela capacidade do runner e pelos tetos. Ao atingir teto, request é recusado antes de produzir efeito; não há fila ilimitada com reserva invisível.

Resultado com custo fornecido lança settlement e libera hold; overshoot preserva custo real reportado e bloqueia próximo trabalho pelo saldo. Custo desconhecido mantém hold e slot até isolamento/ack apropriado; não vira zero nem autoriza retry. Cancelamento antes do lease libera reserva com evidência de que nada iniciou. Após início, cancelamento só terminaliza com ack; resposta tardia não sobrescreve estado e permanece evidência para conciliação owner auditada.

Fontes, chave original, membership, runner/credencial e policy selada/corrente são revalidados antes de lease, heartbeat, efeito/publicação. Restrição cancela trabalho não iniciado; trabalho iniciado sem resultado confiável fica uncertain. Policy nova mais permissiva não amplia manifest ou reserva já selados. Retry de tentativa incerta exige nova autorização, plano e reserva, preservando evidência anterior.

Provas mínimas: centavos fracionários exatos, concorrência em dois projetos da mesma organização, quota/paralelismo na virada do mês, idempotência, revogação/origem após enqueue, hold de gasto unknown, cancelamento/retorno tardio, SQLite/PostgreSQL migrations e teste de processo morto/egress em fixture. Sem chamadas pagas ou tráfego produtivo durante implementação.
