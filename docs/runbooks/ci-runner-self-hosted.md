# CI no Mac — `mac-ci`

A CI do EvalOps usa este Mac (macOS ARM64), seguindo o padrão do fluxo-nexo.
O runner `mac-evalops` é registrado exclusivamente no repositório EvalOps, com
label `mac-ci`; o registro e o serviço do fluxo-nexo continuam independentes.

- Instalação: `/Users/rougger/dev/actions-runner-evalops`, runner 2.337.0.
- Serviço: `actions.runner.rouggerxavier-EvalOps.mac-evalops`, LaunchAgent do usuário.
- O serviço inicia no login e usa `caffeinate -i` para impedir sono por ociosidade.
  Encerrar o serviço remove essa assertion; não impede sono ao fechar a tampa.
- Tokens e credenciais ficam na instalação local do runner, fora do repositório.

## Workflow

`.github/workflows/ci.yml` roda em PRs, pushes em `main` e acionamentos manuais.
Os jobs usam `runs-on: mac-ci`, sem fallback automático para o GitHub hosted.
A exceção é `migrate-postgres`, em `ubuntu-latest`: service containers só rodam
em Linux. Ele depende do orçamento de Actions.
Mac desligado, sem rede ou serviço parado deixa os jobs do `mac-ci` na fila.

A cobertura permanece: API Python 3.12, SDK Python 3.9–3.12, testes e build web
Node 22. `setup-uv` instala Python sem exigir instalação global via sudo; cada
job Python usa um venv em `RUNNER_TEMP`. `npm ci` instala pelo lockfile.
Um único runner executa os jobs do EvalOps em sequência. PRs com commits novos
cancelam runs superadas; push de branch não duplica a CI da PR.

Outros repositórios têm serviços próprios na mesma máquina e podem disputar CPU
e memória. Evite iniciar builds/E2E locais pesados durante uma CI já em execução.
O E2E focal do Quality Gate foi validado localmente; não faz parte deste workflow.

## Operação

```bash
gh api repos/rouggerxavier/EvalOps/actions/runners \
  --jq '.runners[] | {name,os,status,busy,labels:[.labels[].name]}'

cd /Users/rougger/dev/actions-runner-evalops
./svc.sh status
./svc.sh stop
./svc.sh start

gh run list --repo rouggerxavier/EvalOps --workflow ci.yml --limit 5
gh run view <run-id> --repo rouggerxavier/EvalOps --json conclusion,jobs
```

Antes de merge, confira o workflow concluído com sucesso no commit atual da PR.
Esse runner substitui os jobs hosted que não iniciavam por orçamento de Actions;
nenhuma configuração de cobrança foi alterada.
