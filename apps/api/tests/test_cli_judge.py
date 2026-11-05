"""CLI judge: gating, isolation and failures as "not measured", with subprocess simulated."""
from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from app.domain.evaluators import llm_judge
from app.domain.rubrics.parser import parse_rubric_yaml
from app.domain.services import eval_service
from app.infra.llm import cli_judge
from app.infra.llm.pricing import split_provider_model
from app.models import EvaluationRun, EvaluationScore, EvaluatorRow
from app.workers import replay_worker

CONTEXT = {"trace": {"output": {"text": "hi", "assistant_message": "hi"}}}
CONFIG = {"model": "cli:claude/claude-sonnet-5-5", "prompt": "Rate {{ trace.output.assistant_message }}"}
CODEX_CONFIG = {**CONFIG, "model": "cli:codex/gpt-6.1-sol"}
GOOD = json.dumps({"is_error": False, "result": '{"score": 0.9, "reasoning": "ok"}', "total_cost_usd": 0.5})


class FakePopen:
    instances: list["FakePopen"] = []
    outcome: tuple[int, str, str] | Exception = (0, GOOD, "")

    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        self.pid, self.returncode, self.stdin_text = 4242, None, None
        FakePopen.instances.append(self)

    def communicate(self, text=None, timeout=None):
        if text is not None:
            self.stdin_text = text
        if isinstance(FakePopen.outcome, Exception):
            outcome, FakePopen.outcome = FakePopen.outcome, (0, "", "")
            raise outcome
        self.returncode, out, err = FakePopen.outcome
        return out, err


@pytest.fixture(autouse=True)
def local_cli(monkeypatch):
    monkeypatch.setenv("EVALOPS_CLI_JUDGE_ENABLED", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setattr(cli_judge.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(cli_judge, "cli_version", lambda provider: "9.9.9")
    monkeypatch.setattr(cli_judge.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(llm_judge, "call_llm", llm_judge._call_llm)
    FakePopen.instances = []
    FakePopen.outcome = (0, GOOD, "")


def _assert_not_measured(result, slug):
    assert result.raw_output["error"] == slug
    assert result.raw_output["judge_cli"]["provider"]
    assert result.cost_usd is None


def test_success_records_identity_and_unknown_cost():
    result = llm_judge.run(CONTEXT, CONFIG)
    assert result.passed is True and result.score == 0.9
    assert result.cost_usd is None  # the CLI's total_cost_usd is a virtual API price, not spend
    assert result.raw_output["judge_cli"] == {
        "provider": "cli:claude",
        "model": "claude-sonnet-5-5",
        "cli_version": "9.9.9",
    }


def test_tiny_cost_cap_does_not_block_cli():
    assert llm_judge.run(CONTEXT, {**CONFIG, "cost_cap_usd": 0}).passed is True


@pytest.mark.parametrize("config", [CONFIG, CODEX_CONFIG])
def test_argv_has_no_shell_no_tools_and_prompt_on_stdin(config, monkeypatch):
    monkeypatch.setattr(cli_judge, "_TOOLS_CANNOT_BE_DISABLED", set())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-pass")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-pass")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    FakePopen.outcome = (
        0,
        GOOD if config is CONFIG else json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": '{"score": 1}'}}
        ),
        "",
    )
    llm_judge.run(CONTEXT, config)
    call = FakePopen.instances[0]
    assert isinstance(call.argv, list) and "shell" not in call.kwargs
    assert call.stdin_text == "Rate hi" and not any("Rate hi" in arg for arg in call.argv)
    assert not set(call.kwargs["env"]) & {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DATABASE_URL"}
    assert "evalops-judge-" in call.kwargs["cwd"] and call.kwargs["start_new_session"] is True
    if config is CONFIG:
        assert call.argv[call.argv.index("--tools") + 1] == ""
    else:
        assert "shell_tool" in call.argv and call.argv[call.argv.index("--sandbox") + 1] == "read-only"
        assert call.argv[-1] == "-"


@pytest.mark.parametrize(
    "outcome,slug",
    [
        ((1, json.dumps({"is_error": True, "result": "Not logged in · Please run /login"}), ""), "cli_judge_login_required"),
        ((1, "", "OAuth token expired"), "cli_judge_login_required"),
        ((0, json.dumps({"is_error": True, "result": "Claude usage limit reached"}), ""), "cli_judge_rate_limited"),
        ((1, "", "HTTP 429 too many requests"), "cli_judge_rate_limited"),
        ((3, "", "boom sk-secret-token-value /Users/me/.claude"), "cli_judge_failed"),
        ((0, "not json", ""), "cli_judge_invalid_output"),
        ((0, json.dumps({"is_error": False, "result": ""}), ""), "cli_judge_invalid_output"),
    ],
)
def test_claude_failures_are_not_measured(outcome, slug):
    FakePopen.outcome = outcome
    result = llm_judge.run(CONTEXT, CONFIG)
    _assert_not_measured(result, slug)
    assert "secret" not in json.dumps(result.raw_output)


def test_invalid_verdict_is_not_measured():
    FakePopen.outcome = (0, json.dumps({"is_error": False, "result": "no json here"}), "")
    _assert_not_measured(llm_judge.run(CONTEXT, CONFIG), "judge_invalid_response")


def test_codex_stays_off_while_its_tools_cannot_be_disabled():
    _assert_not_measured(llm_judge.run(CONTEXT, CODEX_CONFIG), "cli_judge_tools_not_disabled")
    assert FakePopen.instances == []
    status = {option["provider"]: option["status"] for option in cli_judge.availability()}
    assert status == {"cli:claude": "available", "cli:codex": "cli_judge_tools_not_disabled"}


def test_codex_failures_and_tool_use(monkeypatch):
    monkeypatch.setattr(cli_judge, "_TOOLS_CANNOT_BE_DISABLED", set())
    FakePopen.outcome = (1, json.dumps({"type": "turn.failed", "error": {"message": "rate limit"}}), "")
    _assert_not_measured(llm_judge.run(CONTEXT, CODEX_CONFIG), "cli_judge_rate_limited")
    FakePopen.outcome = (
        0,
        "\n".join(
            json.dumps(event)
            for event in (
                {"type": "item.started", "item": {"type": "command_execution"}},
                {"type": "item.completed", "item": {"type": "agent_message", "text": '{"score": 1}'}},
            )
        ),
        "",
    )
    _assert_not_measured(llm_judge.run(CONTEXT, CODEX_CONFIG), "cli_judge_tool_used")


def test_timeout_kills_process_group(monkeypatch):
    killed = []
    monkeypatch.setattr(cli_judge.os, "killpg", lambda pid, sig: killed.append(pid))
    FakePopen.outcome = subprocess.TimeoutExpired("claude", 1)
    _assert_not_measured(llm_judge.run(CONTEXT, CONFIG), "cli_judge_timeout")
    assert killed == [4242]


def test_missing_cli(monkeypatch):
    monkeypatch.setattr(cli_judge.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli_judge, "cli_version", lambda provider: cli_judge._binary(provider))
    _assert_not_measured(llm_judge.run(CONTEXT, CONFIG), "cli_judge_not_found")
    assert FakePopen.instances == []


@pytest.mark.parametrize(
    "env,slug",
    [
        ({"EVALOPS_CLI_JUDGE_ENABLED": "", "APP_ENV": "local"}, "cli_judge_disabled"),
        ({"EVALOPS_CLI_JUDGE_ENABLED": "1", "APP_ENV": "production"}, "cli_judge_requires_local"),
        ({"EVALOPS_CLI_JUDGE_ENABLED": "1", "APP_ENV": "development"}, "cli_judge_requires_local"),
    ],
)
def test_blocked_before_executing(env, slug, monkeypatch):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    _assert_not_measured(llm_judge.run(CONTEXT, CONFIG), slug)
    assert FakePopen.instances == []
    assert {option["status"] for option in cli_judge.availability()} == {slug}
    with pytest.raises(cli_judge.CliJudgeError):
        cli_judge.call("cli:claude", "m", [{"role": "user", "content": "x"}])


@pytest.mark.parametrize("model", ["cli:claude", "cli:claude/", "cli:claude/--dangerously-skip-permissions", "cli:claude/a b"])
def test_model_must_be_pinned_and_cannot_be_a_flag(model):
    _assert_not_measured(llm_judge.run(CONTEXT, {**CONFIG, "model": model}), "cli_judge_model_required")
    assert FakePopen.instances == []


def test_bare_cli_provider_never_routes_to_openai():
    assert split_provider_model("cli:codex") == ("cli:codex", "")


def test_rubric_rejects_unpinned_cli_model():
    with pytest.raises(ValueError, match="pin a model"):
        parse_rubric_yaml(
            """
slug: s
name: n
description: d
threshold: 0.5
evaluators:
  - id: j
    type: llm_judge
    config:
      model: cli:claude
      prompt: "x {{ trace.output.assistant_message }}"
"""
        )


def test_serial_lock_is_shared_and_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_judge.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setenv("EVALOPS_CLI_JUDGE_LOCK_WAIT_SECONDS", "0")
    with cli_judge._SerialLock():
        with pytest.raises(cli_judge.CliJudgeError, match="cli_judge_busy"):
            cli_judge._SerialLock().__enter__()
    with cli_judge._SerialLock():
        pass  # released on exit


def test_replay_refuses_cli_route():
    with pytest.raises(ValueError, match="not_supported_in_replay"):
        asyncio.run(replay_worker._call_provider("cli:claude", "m", [], override=False))


def _version_row(model):
    return EvaluatorRow(type="llm_judge", config={"model": model})


def test_cli_judge_does_not_spend_org_budget():
    assert eval_service._spends_judge_budget(_version_row("cli:claude/m")) is False
    assert eval_service._spends_judge_budget(_version_row("openrouter/m")) is True


@pytest.mark.parametrize("model", [EvaluationRun, EvaluationScore])
def test_unknown_cost_is_not_replaced_by_a_column_default(model):
    # The ORM swaps an explicit None for a column default on INSERT, which would store unknown as 0.
    column = model.__table__.c.cost_usd
    assert column.nullable is True and column.default is None
