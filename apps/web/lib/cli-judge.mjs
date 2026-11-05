// Plain JS so `node --test` exercises the real rules (package.json has no TS loader).

const EVALUATOR_START = /^(\s*)-\s+id:/;
const TOP_LEVEL_KEY = /^[A-Za-z_]/;

function appendJudge(lines, model) {
  const start = lines.findIndex((line) => /^evaluators:\s*$/.test(line));
  if (start === -1) return null;
  let end = lines.findIndex((line, i) => i > start && TOP_LEVEL_KEY.test(line));
  if (end === -1) end = lines.length;
  while (end > start + 1 && !lines[end - 1].trim()) end -= 1;
  const first = lines.slice(start + 1, end).find((line) => EVALUATOR_START.test(line));
  const pad = first ? first.match(EVALUATOR_START)[1] : "  ";
  const block = [
    `${pad}- id: cli_judge`,
    `${pad}  type: llm_judge`,
    `${pad}  weight: 1.0`,
    `${pad}  config:`,
    `${pad}    model: ${model}`,
    `${pad}    prompt: 'Rate this answer from 0 to 1 and reply only with JSON {"score": <number>, "reasoning": "<why>"}: {{ trace.output.assistant_message }}'`,
  ];
  return [...lines.slice(0, end), ...block, ...lines.slice(end)];
}

/** Points every llm_judge at `model`; adds one when the rubric has none. */
export function setJudgeModel(yaml, model) {
  const lines = yaml.split("\n");
  const starts = lines.flatMap((line, i) => (EVALUATOR_START.test(line) ? [i] : []));
  let found = false;
  starts.forEach((start, n) => {
    let end = starts[n + 1] ?? lines.length;
    const next = lines.findIndex((line, i) => i > start && i < end && TOP_LEVEL_KEY.test(line));
    if (next !== -1) end = next;
    const block = lines.slice(start, end);
    if (!block.some((line) => /^\s*(-\s+)?type:\s*llm_judge\s*$/.test(line))) return;
    found = true;
    const modelAt = block.findIndex((line) => /^\s*model:/.test(line));
    if (modelAt !== -1) {
      lines[start + modelAt] = lines[start + modelAt].replace(/model:.*/, `model: ${model}`);
      return;
    }
    const configAt = block.findIndex((line) => /^\s*config:\s*$/.test(line));
    if (configAt === -1) return;
    const indent = block[configAt].match(/^\s*/)[0];
    lines.splice(start + configAt + 1, 0, `${indent}  model: ${model}`);
    starts.forEach((value, k) => {
      if (k > n) starts[k] = value + 1;
    });
  });
  if (found) return lines.join("\n");
  return (appendJudge(lines, model) ?? lines).join("\n");
}

const STATUS_TEXT = {
  available: "disponível",
  cli_judge_disabled: "desligado: defina EVALOPS_CLI_JUDGE_ENABLED=1",
  cli_judge_requires_local: "indisponível: exige APP_ENV=local",
  cli_judge_tools_not_disabled: "indisponível: não dá para desligar as ferramentas desta CLI",
  cli_judge_not_found: "indisponível: CLI não instalada nesta máquina",
};

export function judgeStatusText(status) {
  return STATUS_TEXT[status] ?? "indisponível";
}
