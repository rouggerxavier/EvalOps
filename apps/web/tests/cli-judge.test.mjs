import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { judgeStatusText, setJudgeModel } from "../lib/cli-judge.mjs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const MODEL = "cli:claude/claude-sonnet-5-5";

test("setJudgeModel: replaces the model of an existing judge only", () => {
  const yaml = `slug: a
evaluators:
  - id: size
    type: length_bounds
    config:
      model: untouched
  - id: judge
    type: llm_judge
    config:
      model: openai/gpt-4o-mini
      prompt: "x"`;
  const out = setJudgeModel(yaml, MODEL);
  assert.match(out, /model: untouched/);
  assert.match(out, /type: llm_judge\n {4}config:\n {6}model: cli:claude\/claude-sonnet-5-5\n/);
  assert.doesNotMatch(out, /gpt-4o-mini/);
});

test("setJudgeModel: inserts the model when the judge has none", () => {
  const out = setJudgeModel(`evaluators:\n  - id: j\n    type: llm_judge\n    config:\n      prompt: "x"`, MODEL);
  assert.match(out, /config:\n {6}model: cli:claude\/claude-sonnet-5-5\n {6}prompt/);
});

test("setJudgeModel: adds a judge inside evaluators, before later sections", () => {
  const out = setJudgeModel(
    `evaluators:\n  - id: size\n    type: length_bounds\nautomatic_fail_conditions: []\n`,
    MODEL,
  );
  assert.ok(out.indexOf("cli_judge") < out.indexOf("automatic_fail_conditions"));
  assert.match(out, /\n {2}- id: cli_judge\n {4}type: llm_judge/);
});

test("setJudgeModel: leaves YAML with no evaluators section alone", () => {
  assert.equal(setJudgeModel("slug: a", MODEL), "slug: a");
});

test("status text says why an option is off", () => {
  assert.match(judgeStatusText("cli_judge_disabled"), /EVALOPS_CLI_JUDGE_ENABLED/);
  assert.match(judgeStatusText("cli_judge_requires_local"), /APP_ENV=local/);
  assert.equal(judgeStatusText("whatever"), "indisponível");
});

test("rubric screen: every YAML form uses the editor and blocks unavailable judges", () => {
  const page = read("../app/o/[org]/p/[project]/rubrics/page.tsx");
  const editor = read("../components/RubricYamlEditor.tsx");
  // Create and new-version forms; no raw YAML textarea is left.
  assert.equal(page.match(/<RubricYamlEditor/g).length, 2);
  assert.doesNotMatch(page, /<textarea[^>]*name="yaml_source"/);
  assert.match(page, /getCliJudges\(\)/);
  assert.match(editor, /disabled=\{option\.status !== "available"\}/);
  assert.match(editor, /Modo local/);
  assert.match(editor, /name="yaml_source"/);
});

test("unknown cost renders as unknown, never $0", () => {
  assert.match(read("../app/o/[org]/p/[project]/evaluations/page.tsx"), /run\.cost_usd === null \? "Sem dados"/);
  assert.match(read("../app/o/[org]/p/[project]/traces/[trace]/trace-evaluations.tsx"), /score\.cost_usd === null \? <span className="t__faint">Sem dados/);
});
