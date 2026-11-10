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
    evaluate.add_argument("--evaluator", choices=["regression.standard@1"], default="regression.standard@1")
    evaluate.add_argument("--idempotency-key", default=None)
    evaluate.add_argument("--fail-on-decision", action="store_true")
    result = commands.add_parser("result")
    result.add_argument("id")
    result.add_argument("--fail-on-decision", action="store_true")
    for command in (discover, evaluate, result):
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
            output = client.evaluate(args.project, args.prediction_set, idempotency_key=args.idempotency_key or str(uuid.uuid4()))
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
