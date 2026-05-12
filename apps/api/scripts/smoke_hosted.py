"""
Hosted smoke check for Phase 7 release validation.

Usage:
    python apps/api/scripts/smoke_hosted.py --base-url https://api.evalops.studio
    python apps/api/scripts/smoke_hosted.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys

import httpx


REQUIRED_PATHS = [
    "/v1/traces",
    "/v1/traces/{trace_id}",
    "/v1/evaluations/run",
    "/v1/projects/{project_id}/rubrics",
    "/v1/projects/{project_id}/prompts",
    "/v1/projects/{project_id}/datasets",
    "/v1/projects/{project_id}/experiments",
    "/v1/traces/{trace_id}/feedback",
    "/v1/exports",
]


def fail(msg: str) -> int:
    print(f"[FAIL] {msg}")
    return 1


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="EvalOps hosted smoke checks")
    parser.add_argument("--base-url", required=True, help="API root URL, e.g. https://api.evalops.studio")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    with httpx.Client(timeout=10.0) as client:
        live = client.get(f"{base_url}/health/liveness")
        if live.status_code != 200 or live.json().get("status") != "ok":
            return fail("/health/liveness is not healthy")
        ok("/health/liveness")

        ready = client.get(f"{base_url}/health/readiness")
        if ready.status_code != 200 or ready.json().get("status") != "ok":
            return fail("/health/readiness is not ready")
        ok("/health/readiness")

        docs = client.get(f"{base_url}/docs")
        if docs.status_code != 200:
            return fail("/docs is unavailable")
        ok("/docs")

        openapi = client.get(f"{base_url}/openapi.json")
        if openapi.status_code != 200:
            return fail("/openapi.json is unavailable")
        schema = openapi.json()
        if "paths" not in schema:
            return fail("OpenAPI schema has no paths")
        for required in REQUIRED_PATHS:
            if required not in schema["paths"]:
                return fail(f"Missing OpenAPI path: {required}")
        ok("OpenAPI required paths")

    print("[OK] smoke complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
