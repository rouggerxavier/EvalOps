# Diagnóstico de Performance WSL — EvalOps

## 1. Veredito executivo
- Causa mais provável: degradação severa no runtime de testes backend neste ambiente WSL2/Linux (Python 3.14.4 + FastAPI TestClient + SQLite), com execução de `pytest` travando/estourando 15 min sem output útil mesmo em suítes isoladas.
- Causas secundárias: `test_phase11.db` e `evalops.db` persistidos no repo, teste com engine SQLite própria fora do isolamento global (`tests/test_phase11_contracts_ux.py`), e volume grande de hashing/auth + setup/teardown de schema por teste.
- Confirmado por evidência:
  - Repo está em filesystem Linux/ext4 (`/home/...`), não em `/mnt/c`.
  - `node_modules`, `.venv`, `.next` estão em ext4 no WSL.
  - Frontend está rápido (test 1.57s; build 27.80s).
  - Backend `pytest` (suite completa e suites críticas) excede 15 min/timeout no ambiente atual.
- Hipóteses (não totalmente comprovadas neste run): diferença de comportamento/overhead do Python 3.14.4 em relação ao ambiente Windows anterior; impacto de lock/IO do SQLite sob concorrência de fixtures/TestClient.
- O que fazer primeiro: focar benchmark/controlado no backend (Python+pytest+SQLite), não no filesystem path (que já está correto).

## 2. Ambiente atual
- OS/WSL:
  - `Linux ... 6.6.87.2-microsoft-standard-WSL2`
  - `Ubuntu 26.04 LTS`
  - `wsl.exe --version` falhou no shell WSL (`UtilBindVsockAnyPort`).
- Path do repo:
  - `/home/rouggerxavier/dev/evalops`
  - classificado como **Bom** (ext4 Linux).
- Filesystem:
  - `df -h .` => `/dev/sdd` ext4.
  - `/mnt/c` existe via 9p/DrvFS, mas repo não está lá.
- CPU/RAM/swap:
  - CPU: 12 vCPU (Ryzen 5 5600 host).
  - RAM: 7.7 GiB total, 5.6 GiB disponível no momento.
  - Swap: 2.0 GiB (0 usado).
- Python/Node/npm:
  - `python`: ausente no PATH global.
  - `python3`: 3.14.4.
  - `apps/api/.venv/bin/python`: 3.14.4.
  - `node`: v24.15.0; `npm`: 11.12.1.
- Venv:
  - `apps/api/.venv` presente em ext4.
- Banco de teste:
  - `apps/api/tests/conftest.py` cria DB temporário em `tempfile.mkdtemp(...)` (OS temp dir) com `NullPool`.
  - Ainda existem no repo: `apps/api/evalops.db` e `apps/api/test_phase11.db`.

## 3. Comparação com baseline anterior
- Baseline documentado (arquivo `docs/plans/baseline.md`):
  - `test_phase8_p0_security.py`: ~100.15s.
  - `test_phase9_auth_hardening.py`: ~177.41s.
  - `test_phase10_audit_privacy_exports.py`: ~265.82s.
  - Também há registros de “131 passed” e execuções completas verdes após Fix-7B.3.
- Medido agora (2026-05-15, WSL):
  - `pytest tests` completo: sem output útil e interrompido por limite operacional (>15 min).
  - `phase8`, `phase9`, `phase10`, `phase12`: todos extrapolaram 15 min (timeouts/interrupt).
- Mudanças observáveis:
  - Runtime atual usa Python 3.14.4.
  - Persistência de arquivos DB locais no repo ainda existe.
  - Frontend não apresenta lentidão equivalente.

## 4. Tempos medidos

| comando | tempo | resultado | top testes lentos | observações |
|---|---:|---|---|---|
| `cd apps/api && .venv/bin/python -m pytest tests -q --tb=short -p no:warnings --durations=25` | >15m | interrompido (sem output útil) | n/a | trava operacional no backend |
| `... pytest tests/test_phase8_p0_security.py ... --durations=10` | >15m | interrompido | n/a | sem flush de progresso |
| `... pytest tests/test_phase9_auth_hardening.py ... --durations=10` | 15m | timeout (exit 124) | n/a | não concluiu |
| `... pytest tests/test_phase10_audit_privacy_exports.py ... --durations=10` | 15m | timeout (exit 124) | n/a | não concluiu |
| `... pytest tests/test_phase12_quota_eval_storage.py ... --durations=10` | 15m | timeout (exit 124) | n/a | não concluiu |
| `cd apps/web && npm run test` | 1.57s | passou | n/a | rápido |
| `cd apps/web && npx tsc --noEmit` | 9.35s | falhou | n/a | `.next/types/**/*.ts` ausente |
| `cd apps/web && npm run build` | 27.80s | passou | n/a | Next compilou em ~3.0s |
| micro-benchmark `hash_password/verify_password` | ~0.038s / ~0.029s | ok | n/a | argon2 não explica sozinho timeout de >15m |

## 5. Gargalos prováveis
- P0: backend `pytest` no ambiente atual sem confiabilidade temporal (timeouts >15 min em suites-chave).
- P1: SQLite + TestClient + fixtures (create/drop por teste) com comportamento patológico no runtime atual.
- P1: engine SQLite dedicada em `test_phase11_contracts_ux.py` (`sqlite:///./test_phase11.db`) fora da estratégia comum de isolamento.
- P2: resíduos `evalops.db`/`test_phase11.db` no repo podem influenciar execuções locais/confusão operacional.
- P2: uso de Python 3.14.4 (novo) pode estar pior para essa stack específica vs ambiente Windows anterior.
- P3: impacto de contexto gigante em prompts (docs grandes + histórico longo) pode inflar duração de sessões de agente.

## 6. Testes mais lentos
- Não foi possível obter `--durations` porque as suítes backend não concluíram dentro de 15 minutos.
- Suites mais críticas pelo comportamento atual:
  - `tests/test_phase8_p0_security.py` (timeout/interrupção >15m)
  - `tests/test_phase9_auth_hardening.py` (timeout 15m)
  - `tests/test_phase10_audit_privacy_exports.py` (timeout 15m)
  - `tests/test_phase12_quota_eval_storage.py` (timeout 15m)
- Possível causa: interação entre TestClient, setup de banco e runtime/IO SQLite nesse ambiente.
- Recomendação (sem implementar): rodar essas suites com telemetria de lock/SQL e profiling (`pytest --setup-show --durations -vv`, sqlite trace), em ambiente controlado com Python alternativo e DB em tmpfs.

## 7. WSL/filesystem
- Repo está no lugar certo? **Sim** (`/home/...`, ext4).
- `.venv`, `node_modules`, `.next` no lugar certo? **Sim**, todos no ext4 WSL.
- DB temporário de testes comum em lugar certo? **Sim**, em `tempfile` (tmp dir Linux) no `conftest` global.
- Risco de `/mnt/c`: baixo neste estado atual (não é a localização do repo).
- Conclusão: filesystem path não é a causa primária desta lentidão específica.

## 8. Python/SQLite/TestClient
- Achados sobre DB:
  - `tests/conftest.py` (Fix-7B.3) usa DB temporário e `NullPool` para reduzir lock.
  - Ainda existe teste com DB próprio fixo em arquivo local: `tests/test_phase11_contracts_ux.py` usa `sqlite:///./test_phase11.db`.
  - Arquivos locais presentes: `apps/api/evalops.db`, `apps/api/test_phase11.db`.
- Locks restantes:
  - Nesta auditoria não houve erro explícito de lock porque as suítes não chegaram a finalizar/emitir traceback; mas o padrão de timeout é compatível com regressão de runtime/IO/concurrency em backend.
- Engine própria fora de fixture comum:
  - Sim, `test_phase11_contracts_ux.py` cria `test_engine` específico.
- Argon2/bcrypt:
  - Projeto usa Argon2 em `app/security.py` (`memory_cost=19456`, `time_cost=2`).
  - Medição unitária de hash/verify (~38ms/~29ms) não sustenta, sozinha, timeout de 15 min.
- Sessões/conexões:
  - Estratégia global atual já tenta evitar conexões em pool (`NullPool`).

## 9. Node/Next
- Build/test timings:
  - `npm run test`: rápido (1.57s).
  - `npm run build`: rápido (27.80s).
- Cache:
  - `.next` existe em ext4 e build foi normal.
- `npx tsc --noEmit`:
  - Falhou por referências a `.next/types/**/*.ts` inexistentes no momento da execução isolada.
- Conclusão: frontend não é o gargalo de performance observado.

## 10. Agentes e contexto
- Risco de prompts >150k contexto: **alto** se sessão mantiver baseline/roadmap/auditorias grandes.
- Arquivos grandes relevantes em `docs/`:
  - `docs/plans/baseline.md` ~83.9 KB
  - `docs/plans/evalops-fix-7b-execution-plan.md` ~51.7 KB
  - `docs/plans/evalops-remediation-roadmap.md` ~46.0 KB
- Recomendações operacionais:
  - usar `/clear` entre subfases longas;
  - usar `/compact` no meio de fases extensas;
  - preferir prompts menores orientados por comando objetivo;
  - evitar colar logs completos quando um resumo com trechos-chave basta;
  - usar `timeout` em comandos longos para evitar sessões bloqueadas.

## 11. Recomendações
- Imediatas, sem mexer em código:
  - Rodar backend em lotes menores com `timeout` e logs de progresso verbosos.
  - Garantir execução serial (sem múltiplos agentes/testes/builds concorrentes).
  - Limpar contexto de agente entre blocos pesados (`/clear`/`/compact`).
- Ajustes de ambiente:
  - Validar benchmark A/B com Python 3.12 vs 3.14 no WSL.
  - Aumentar memória/swap disponível para WSL (se uso real crescer durante testes).
  - Confirmar exclusões no Defender para pastas de projeto/artefatos (sugestão apenas).
- Ajustes de testes:
  - Isolar suites mais pesadas por arquivo e capturar profiling de setup/DB.
  - Evitar mistura de múltiplas fontes de engine SQLite local no mesmo fluxo.
- Ajustes de prompts/agentes:
  - Quebrar auditorias em etapas menores com critérios de parada e timeout.
  - Anexar só dados necessários (não carregar docs gigantes em toda rodada).
- Melhorias futuras no código (não aplicadas aqui):
  - convergir todos os testes para a mesma estratégia de DB de teste;
  - avaliar backend tests em Postgres de teste para reduzir fragilidade de lock/IO SQLite.

## 12. Plano de ação sugerido
- [ ] Executar benchmark backend com Python 3.12 no mesmo WSL e comparar com 3.14.
- [ ] Rodar `pytest` pesado sempre com `timeout` + `-vv --setup-show` + coleta de durations.
- [ ] Isolar/medir `phase8/9/10/12` individualmente com logging mínimo de DB.
- [ ] Verificar e evitar coexistência de DBs fixos locais em fluxos de suite completa.
- [ ] Garantir que apenas 1 runner pesado rode por vez (sem concorrência de agentes/builds).
- [ ] Aplicar higiene de contexto (`/clear`, `/compact`, prompts menores).
- [ ] Opcional: revisar exclusões do Defender para diretórios de build/teste.
- [ ] Decidir execução principal: manter WSL para frontend e operações gerais; backend pesado condicionado a benchmark A/B Python/runtime.
