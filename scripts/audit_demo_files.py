"""Read-only audit of the files referenced by the cases of a PrevaIQ environment.

Lists the cases (``GET /api/applications``), reads each one (``GET /api/applications/{id}``)
and checks every ``files[].filename`` with ``GET /api/applications/{id}/files/{name}``
(status only, nothing is downloaded or written).

Usage (PowerShell):
    $env:PREVAIQ_API_KEY = "<key>"          # read from the environment, never printed
    python scripts/audit_demo_files.py --api-url https://<api-host> [--json]

The API URL can also come from ``PREVAIQ_API_URL``. Exit code 1 when a referenced file is
missing (or a case could not be read). ``--json`` prints
``{"apps": N, "refs": N, "missing": {app_id: {"persona": ..., "files": [...]}}}``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib.parse import quote

import httpx

RETRYABLE = {502, 503, 504}
ATTEMPTS = 3


def call(client: httpx.Client, url: str, stream: bool = False) -> httpx.Response:
    """GET with a few retries on transient errors; streamed bodies are not downloaded."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = client.send(client.build_request("GET", url), stream=stream)
            if stream:
                response.close()
            if response.status_code not in RETRYABLE or attempt == ATTEMPTS:
                return response
        except httpx.TransportError:
            if attempt == ATTEMPTS:
                raise
        time.sleep(3 * attempt)
    raise AssertionError("unreachable")


def list_cases(client: httpx.Client) -> list[dict[str, Any]]:
    response = call(client, "/api/applications")
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    return payload.get("applications") or payload.get("items") or []


def audit(client: httpx.Client) -> tuple[dict[str, Any], dict[str, int], list[str]]:
    cases = list_cases(client)
    refs, missing, totals, errors = 0, {}, {}, []
    for case in cases:
        app_id = case.get("id")
        try:
            response = call(client, f"/api/applications/{quote(app_id, safe='')}")
            response.raise_for_status()
            detail = response.json()
            files = detail.get("files") or []
            absent = []
            for stored in files:
                name = stored.get("filename") or stored.get("name")
                refs += 1
                url = f"/api/applications/{quote(app_id, safe='')}/files/{quote(name, safe='')}"
                if call(client, url, stream=True).status_code != 200:
                    absent.append(name)
        except httpx.HTTPError as exc:
            errors.append(f"{app_id}: {exc}")
            continue
        if absent:
            missing[app_id] = {"persona": detail.get("persona"), "files": absent}
            totals[app_id] = len(files)
    return {"apps": len(cases), "refs": refs, "missing": missing}, totals, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--api-url",
        default=os.environ.get("PREVAIQ_API_URL"),
        help="API base URL (default: $PREVAIQ_API_URL)",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    parser.add_argument("--timeout", type=float, default=60.0, help="Request timeout (seconds)")
    args = parser.parse_args(argv)

    if not args.api_url or not args.api_url.startswith(("http://", "https://")):
        parser.error("an http(s) API URL is required (--api-url or PREVAIQ_API_URL)")
    api_key = os.environ.get("PREVAIQ_API_KEY")
    if not api_key:
        parser.error("PREVAIQ_API_KEY is not set")

    timeout = httpx.Timeout(args.timeout, connect=30.0)
    with httpx.Client(
        base_url=args.api_url.rstrip("/"), headers={"X-API-Key": api_key}, timeout=timeout
    ) as client:
        try:
            report, totals, errors = audit(client)
        except httpx.HTTPError as exc:
            print(f"Cannot list the cases: {exc}", file=sys.stderr)
            return 2

    missing_count = sum(len(item["files"]) for item in report["missing"].values())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"apps {report['apps']} | refs {report['refs']} | missing {missing_count}")
        for app_id, item in sorted(report["missing"].items()):
            print(
                f"{app_id:18} {item['persona'] or '-':22} missing "
                f"{len(item['files'])}/{totals[app_id]}: {', '.join(item['files'])}"
            )
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if missing_count or errors else 0


if __name__ == "__main__":
    sys.exit(main())
