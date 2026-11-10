"""Measure the bounded offline HTTP vertical against a disposable local API."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import statistics
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if urlparse(args.api_url).hostname not in {"127.0.0.1", "localhost"} or args.runs < 1:
        parser.error("use a disposable local API and at least one run")
    stamp = uuid4().hex
    with httpx.Client(base_url=args.api_url.rstrip("/") + "/", timeout=120) as http:
        response = http.post("auth/register", json={"email": f"benchmark-{stamp}@example.test", "name": "Offline benchmark",
            "password": "Benchmark-" + uuid4().hex + "!", "org_name": "Benchmark " + stamp, "project_name": "Offline"})
        response.raise_for_status()
        session = response.json()
        project = session["workspace"]["project_id"]
        human = {"Authorization": "Bearer " + session["token"]}
        def post(path, payload, headers):
            response = http.post(path, json=payload, headers={**headers, "Idempotency-Key": uuid4().hex})
            response.raise_for_status()
            return response.json()
        principal = post(f"projects/{project}/service-principals", {"name": "Benchmark"}, human)
        key = post(f"projects/{project}/api-keys", {"name": "Benchmark", "environment": "dev", "scopes": ["read","write","evaluate"],
            "service_principal_id": principal["id"], "expires_at": (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}, human)
        headers = {"X-EvalOps-Key": key["key"]}
        items = [{"sample_id": str(i), "input": {"x": i}, "expected_output": {"value": i}} for i in range(10000)]
        dataset = post(f"projects/{project}/datasets", {"slug": "benchmark", "task_type": "regression", "task_schema": {"target": {"name": "price", "unit": "BRL"}},
            "access": {"environment": "dev"}, "items": items}, headers)
        snap = post(f"datasets/{dataset['id']}/snapshots", {"environment": "dev"}, headers)
        model = post(f"projects/{project}/model-versions", {"model": {"name": "external", "version_ref": "v1"}, "access": {"environment": "dev"}}, headers)
        predictions = post(f"projects/{project}/prediction-sets", {"environment": "dev", "snapshot_id": snap["id"], "model_version_id": model["id"],
            "rows": [{"sample_id": str(i), "prediction": {"value": i+0.5}} for i in range(10000)]}, headers)
        timings = []
        for _ in range(args.runs):
            start = perf_counter()
            result = post(f"projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers)
            timings.append(perf_counter()-start)
            assert result["n_valid"] == result["n_total"] == 10000
            response = http.get(f"task-evaluations/{result['id']}/metrics", headers=headers)
            response.raise_for_status()
            fact = next(fact for fact in response.json()["data"] if fact["definition_id"] == "regression.mae" and fact["scope"] == "dataset")
            assert abs(fact["value"]-0.5) < 1e-12
        import math
        print(json.dumps({"rows": 10000, "runs": args.runs, "seconds": timings,
            "median_seconds": statistics.median(timings), "p95_seconds": sorted(timings)[math.ceil(args.runs*0.95)-1],
            "scope": "HTTP authorization, source checks, calculation, hashes and persistence; excludes setup and metric GET"}))


if __name__ == "__main__":
    main()
