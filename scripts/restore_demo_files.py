"""Restore the demo files of the PrevaIQ demo cases through the API (idempotent).

For every entry of ``assets/demo-prevaiq/seeded/manifest.json``:
``GET /api/applications/{app_id}/files/{filename}`` → 200: already present, skipped;
otherwise the repo file is uploaded with ``PUT`` on the same URL (raw body). The API only
accepts files the case already references and checks the content signature.

Usage (PowerShell):
    $env:PREVAIQ_API_KEY = "<key>"          # read from the environment, never printed
    python scripts/restore_demo_files.py --api-url https://<api-host> --dry-run
    python scripts/restore_demo_files.py --api-url https://<api-host> [--only app-hab-004]

The API URL can also come from ``PREVAIQ_API_URL``. Exit code 1 when a file failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "assets" / "demo-prevaiq" / "seeded" / "manifest.json"
RETRYABLE = {502, 503, 504}
ATTEMPTS = 3


def file_url(app_id: str, filename: str) -> str:
    return f"/api/applications/{quote(app_id, safe='')}/files/{quote(filename, safe='')}"


def call(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send with a few retries on transient errors; GET bodies are never downloaded."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            stream = method == "GET"
            response = client.send(client.build_request(method, url, **kwargs), stream=stream)
            if stream:
                response.close()
            if response.status_code not in RETRYABLE or attempt == ATTEMPTS:
                return response
        except httpx.TransportError:
            if attempt == ATTEMPTS:
                raise
        time.sleep(3 * attempt)
    raise AssertionError("unreachable")


def detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))[:200]
    except ValueError:
        return response.text[:200]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--api-url",
        default=os.environ.get("PREVAIQ_API_URL"),
        help="API base URL (default: $PREVAIQ_API_URL)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Check only, never upload")
    parser.add_argument(
        "--only", action="append", metavar="APP_ID", help="Limit to these cases (repeatable)"
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout (seconds)")
    args = parser.parse_args(argv)

    if not args.api_url or not args.api_url.startswith(("http://", "https://")):
        parser.error("an http(s) API URL is required (--api-url or PREVAIQ_API_URL)")
    api_key = os.environ.get("PREVAIQ_API_KEY")
    if not api_key:
        parser.error("PREVAIQ_API_KEY is not set")

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))["files"]
    if args.only:
        unknown = set(args.only) - {entry["app_id"] for entry in entries}
        if unknown:
            parser.error(f"not in the manifest: {', '.join(sorted(unknown))}")
        entries = [entry for entry in entries if entry["app_id"] in args.only]

    restored, present, pending, failed = 0, 0, 0, []
    timeout = httpx.Timeout(args.timeout, connect=30.0)
    with httpx.Client(
        base_url=args.api_url.rstrip("/"), headers={"X-API-Key": api_key}, timeout=timeout
    ) as client:
        for entry in entries:
            label = f"{entry['app_id']}/{entry['filename']}"
            path = ROOT / entry["path"]
            url = file_url(entry["app_id"], entry["filename"])
            try:
                if not path.is_file():
                    raise RuntimeError(f"local file missing: {entry['path']}")
                status = call(client, "GET", url).status_code
                if status in (401, 403):
                    print(f"Authentication refused (HTTP {status}): check PREVAIQ_API_KEY.")
                    return 2
                if status == 200:
                    present += 1
                    print(f"  present   {label}")
                    continue
                if status != 404:
                    raise RuntimeError(f"GET returned HTTP {status}")
                if args.dry_run:
                    pending += 1
                    print(f"  missing   {label} (would upload {path.stat().st_size // 1024} KB)")
                    continue
                response = call(
                    client,
                    "PUT",
                    url,
                    content=path.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"},
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"PUT returned HTTP {response.status_code}: {detail(response)}"
                    )
                restored += 1
                print(f"  restored  {label} ({path.stat().st_size // 1024} KB)")
            except (RuntimeError, httpx.HTTPError) as exc:
                failed.append(label)
                print(f"  FAILED    {label}: {exc}")

    summary = f"restored {restored} | already present {present} | failed {len(failed)}"
    if args.dry_run:
        summary = (
            f"dry run: to restore {pending} | already present {present} | failed {len(failed)}"
        )
    print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
