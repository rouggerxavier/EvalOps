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


def test_investigation_cli_preserves_revision_and_receipt(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EVALOPS_API_KEY", "test-secret")
    state = {"title": "Continue", "next_steps": ["Review evidence"]}
    source = tmp_path / "state.json"
    source.write_text(json.dumps(state), encoding="utf-8")
    class Client:
        def __init__(self, **kwargs):
            pass
        def update_investigation(self, identifier, payload, **kwargs):
            assert identifier == "inv" and payload == state
            assert kwargs == {"revision": 3, "idempotency_key": "receipt"}
            return {"id": identifier, "revision": 4, **payload}
    monkeypatch.setattr(cli, "Client", Client)
    assert cli.main(["investigation-update", "inv", "--revision", "3", "--file", str(source), "--idempotency-key", "receipt"]) == 0
    assert json.loads(capsys.readouterr().out)["revision"] == 4
    source.write_bytes(b"\xff")
    assert cli.main(["investigation-update", "inv", "--revision", "3", "--file", str(source), "--idempotency-key", "receipt"]) == 2
    assert not capsys.readouterr().out


def test_cli_classification_routes_explicit_version(monkeypatch, capsys):
    monkeypatch.setenv("EVALOPS_API_KEY", "test-secret")
    class Client:
        def __init__(self, **kwargs):
            pass
        def evaluate(self, project, predictions, **kwargs):
            assert (project, predictions) == ("p", "pred")
            assert kwargs == {"evaluator": "classification.standard", "idempotency_key": "op"}
            return {"id": "evaluation", "decision": "inconclusive"}
    monkeypatch.setattr(cli, "Client", Client)
    assert cli.main(["evaluate", "--project", "p", "--prediction-set", "pred", "--evaluator", "classification.standard@1", "--idempotency-key", "op", "--fail-on-decision"]) == 4
    assert json.loads(capsys.readouterr().out)["id"] == "evaluation"


def test_cli_imports_external_capture_without_dispatch(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("EVALOPS_API_KEY", "test-secret")
    payload = {"manifest": {}, "result": {"cost": {"state": "unknown"}}}
    source = tmp_path / "capture.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    class Client:
        def __init__(self, **kwargs):
            pass
        def import_execution(self, project, body, **kwargs):
            assert project == "p" and body == payload and kwargs == {"idempotency_key": "capture"}
            return {"id": "execution", "capture_origin": "external_import"}
    monkeypatch.setattr(cli, "Client", Client)
    assert cli.main(["execution-import", "--project", "p", "--file", str(source), "--idempotency-key", "capture"]) == 0
    assert json.loads(capsys.readouterr().out)["capture_origin"] == "external_import"
