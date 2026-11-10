import json

from evalops import cli


def test_cli_preserves_result_and_quality_exit(monkeypatch, capsys):
    monkeypatch.setenv("EVALOPS_API_KEY", "test-secret")
    payload = {"id": "evaluation", "decision": "inconclusive", "coverage": None, "decision_reasons": ["no_quality_policy"]}
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-secret"
        def task_result(self, identifier):
            assert identifier == "evaluation"
            return dict(payload)
        def task_metrics(self, identifier):
            return {"data": [{"value": -1, "unit": "1", "reason": None}]}
    monkeypatch.setattr(cli, "Client", Client)
    assert cli.main(["result", "evaluation", "--json", "--fail-on-decision"]) == 4
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {**payload, "metrics": [{"value": -1, "unit": "1", "reason": None}]}
    assert not captured.err and "test-secret" not in captured.out


def test_cli_missing_credential_is_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("EVALOPS_API_KEY", raising=False)
    assert cli.main(["discover", "--project", "p", "--json"]) == 2
    assert not capsys.readouterr().out
