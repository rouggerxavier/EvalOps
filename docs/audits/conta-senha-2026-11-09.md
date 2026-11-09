# Revisão da fatia Conta — 2026-11-09

## Escopo

- Alvo: troca autenticada de senha, JWTs pessoais, `/account` e link na EvoTopbar.
- Lens: access control.
- Branch: `feat/troca-senha-segura`, base `1abbeb5`.
- Fora do escopo: auditoria geral do produto, Grankasa, recuperação pública/SMTP,
  topologia de proxy/login, API keys de projeto e redesign.

## Resultado

Verificações locais aprovadas, com revisão independente de segurança/UI solicitada
pelo integrador antes de publicação. Recuperação pública não foi implementada.

## Entradas e autoridade

| Ator/entrada | Recurso e ação | Fronteira e resultado |
| --- | --- | --- |
| Anônimo ou apenas chave de projeto | Trocar senha pessoal | `401`, exige JWT pessoal real |
| Usuário com JWT e senha atual inválida | Própria senha | `400 invalid_credentials`, nada altera |
| Usuário autenticado envia email/user_id de terceiro | Senha de outro usuário | Corpo não define alvo; somente o usuário do JWT pode mudar |
| Usuário com senha atual válida | Própria senha/sessões | Commit único hash+versão; JWTs anteriores rejeitados |
| JWT legado, versão ausente | Sessão pessoal | Aceito como zero somente enquanto DB=0 |
| Claim bool/float/string/null/versão divergente | Sessão pessoal | `401`, sem coerção |
| Cookie ausente com fallback dev ativo | Conta/Server Action | Redireciona ao login; fallback não autoriza |
| Origin estrangeira com cookie válido | Server Action real | Next rejeita o POST antes da mutação |

## Achados corrigidos

| Severidade | Local | Evidência / ataque | Correção e prova |
| --- | --- | --- | --- |
| Alta | `main.py`, validação da nova rota | Erro 422 padrão pode refletir senha em `input` | Handler só dessa rota retorna código fixo; testes com senha curta/longa, tipo inválido e JSON malformado, sem valores em resposta/log |
| Média | `/account`, query de erro | `error=__proto__` expõe propriedade herdada ao renderizador | `Object.hasOwn`; SSR adversarial cobre também `constructor`, `toString`, `hasOwnProperty` |
| Média | `scripts/seed_dev.py` | Bearer dev sem versão falharia após uma troca | Emissor usa helper e versão corrente; teste com versão 4 e `.env.local` exclusivamente temporário |
| Alta | Concorrência/identity map | Duas sessões com snapshot 0 poderiam sobrescrever a troca | Releitura sob lock+comparação e UPDATE condicional; duas sessões reais terminam em 204+401, versão final 1, senha vencedora válida |

## Verificação

- API completa: `642 passed, 14 skipped` após o handler de validação. A adição final
  do teste do emissor dev foi verificada na suíte focada.
- Fatia Conta: 30 testes focados em SQLite e Postgres16 dedicado, incluindo
  rollback após flush, duas sessões/snapshots concorrentes, JWT legado/novo,
  revogação global, isolamento do alvo, limites de 8/256/257 caracteres não BMP
  e chave de API ainda autenticando.
- Migration: schema isolado com usuário existente em 0012; upgrade preservou hash
  e preencheu versão zero; downgrade até 0012/upgrade e `alembic check` sem operações novas.
- Web: 236 testes, TypeScript e `CI=1 npm run build`.
- Navegador: quatro testes Playwright, incluindo 1280/375 px, teclado, sessão ausente
  com fallback dev, confirmação inválida, senha atual inválida, origem estrangeira,
  troca real, cookie removido, token anterior 401 e login com a nova senha.
  Senha atual de 200 emojis e nova de oito emojis atravessam os campos/ação intactas.
  O sino aberto permanece dentro do viewport nos dois tamanhos.
- Detector mecânico Impeccable sobre os alvos UI alterados: `[]`.
- Estilos/tokens e contexto `PRODUCT.md`/`DESIGN.md` herdados; nenhuma mudança de
  sistema visual. Capturas inspecionadas nos dois tamanhos, sem overflow/overlap.

Runtime de QA: API 18133, web 3133, DB exclusivo `evalops_account_test` na porta 15633.
O pool ARQ foi substituído por um stub que retorna `None`; nenhum Redis compartilhado,
email ou provedor LLM foi chamado. Os testes API usam SQLite temporário por padrão;
a fixture PG cria e remove somente seu schema aleatório no alvo explicitamente guardado.

Capturas: [Conta 1280](img/conta-1280.jpg), [Conta 375](img/conta-375.jpg),
[barra 1280](img/conta-topbar-1280.jpg), [barra 375](img/conta-topbar-375.jpg),
[sino aberto 375](img/conta-sino-375.jpg).

## Risco residual e revisão humana

O limite em memória protege por processo; distribuição exige o Redis já suportado.
Requisições autenticadas antes do commit podem terminar. Não houve teste com senha
ou banco pessoal, navegadores além do Chromium, SMTP ou produção.

**Rolling deploy e rollback precisam preservar o verificador de versão.** Código
anterior revalidaria JWTs revogados; não baixe versões nem remova a coluna após uso.
Sequência segura e alternativa com rotação de segredo em [operação](../ops/conta-senha.md).
