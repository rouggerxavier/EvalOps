"""Offline evaluation CLI. Credentials come only from environment variables."""
import argparse
import json
import os
import sys
import uuid

import httpx
from evalops.client import Client


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evalops")
    commands = parser.add_subparsers(dest="command", required=True)
    discover = commands.add_parser("discover")
    discover.add_argument("--project", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--project", required=True)
    evaluate.add_argument("--prediction-set", required=True)
    evaluate.add_argument("--evaluator", choices=["regression.standard@1", "classification.standard@1"], default="regression.standard@1")
    evaluate.add_argument("--idempotency-key", default=None)
    evaluate.add_argument("--fail-on-decision", action="store_true")
    result = commands.add_parser("result")
    result.add_argument("id")
    result.add_argument("--fail-on-decision", action="store_true")
    investigation = commands.add_parser("investigation")
    investigation.add_argument("id")
    investigation.add_argument("--history", action="store_true")
    inv_create = commands.add_parser("investigation-create")
    inv_create.add_argument("--project", required=True)
    inv_create.add_argument("--environment", choices=["dev", "staging", "prod"], required=True)
    inv_create.add_argument("--file", required=True)
    inv_create.add_argument("--idempotency-key", required=True)
    inv_update = commands.add_parser("investigation-update")
    inv_update.add_argument("id")
    inv_update.add_argument("--revision", type=int, required=True)
    inv_update.add_argument("--file", required=True)
    inv_update.add_argument("--idempotency-key", required=True)
    for command in (discover, evaluate, result, investigation, inv_create, inv_update):
        command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    key = os.environ.get("EVALOPS_API_KEY")
    if not key:
        print("EVALOPS_API_KEY is required", file=sys.stderr)
        return 2
    client = Client(api_key=key, api_url=os.environ.get("EVALOPS_API_URL", "http://localhost:8000/v1"))
    try:
        if args.command == "discover":
            output = client.discover(args.project)
        elif args.command == "evaluate":
            output = client.evaluate(args.project, args.prediction_set, idempotency_key=args.idempotency_key or str(uuid.uuid4()), evaluator=args.evaluator.split("@")[0])
        elif args.command == "investigation":
            output = client.investigation_history(args.id) if args.history else client.get_investigation(args.id)
        elif args.command in {"investigation-create", "investigation-update"}:
            try:
                with open(args.file, encoding="utf-8") as stream:
                    state = json.load(stream)
            except (OSError, UnicodeError, json.JSONDecodeError):
                print("Cannot read the investigation JSON file", file=sys.stderr)
                return 2
            if not isinstance(state, dict):
                print("Investigation state must be a JSON object", file=sys.stderr)
                return 2
            if args.command == "investigation-create":
                output = client.create_investigation(args.project, {"environment": args.environment, "state": state}, idempotency_key=args.idempotency_key)
            else:
                output = client.update_investigation(args.id, state, revision=args.revision, idempotency_key=args.idempotency_key)
        else:
            output = client.task_result(args.id)
            output["metrics"] = client.task_metrics(args.id)["data"]
        print(json.dumps(output, ensure_ascii=False, allow_nan=False))
        if getattr(args, "fail_on_decision", False):
            return 3 if output.get("decision") == "fail" else 4 if output.get("decision") in ("review", "inconclusive") else 0
        return 0
    except httpx.HTTPStatusError as exc:
        print(f"API returned HTTP {exc.response.status_code}", file=sys.stderr)
        return 2 if exc.response.status_code == 422 else 1
    except (httpx.TransportError, ValueError):
        print("Request failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
