"""Evaluate the document pipeline before rolling out a change.

Runs every golden case (tests/fixtures/eval/manifest.json) through extraction ->
validation -> analysis (and optionally a MAF workflow) for each variant, then
compares quality, completeness, citations, latency, tokens and cost against the
first (baseline) variant.

Usage:
    python scripts/eval_pipeline.py \
        --variant baseline \
        --variant chat_completions:AGENTS_OPENAI_API=chat_completions \
        --workflow express

A variant is ``name[:ENV=VALUE,ENV=VALUE]``; env overrides apply for that variant only.
Reports go to .tmp/eval/<timestamp>/ (results.json + summary.md).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "eval" / "manifest.json"
DEFAULT_PRICES = ROOT / "tests" / "fixtures" / "eval" / "prices.json"
METRICS = (
    "quality",
    "completeness",
    "citations",
    "extraction_s",
    "analysis_s",
    "workflow_s",
    "tokens",
    "cost",
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("\u00a0", " ").split())


def _share(expected: List[str], haystack: str) -> float | None:
    if not expected:
        return None
    hay = _norm(haystack)
    return round(sum(_norm(e) in hay for e in expected) / len(expected), 3)


def _field_values(fields: Dict[str, Any] | None) -> str:
    return "\n".join(
        json.dumps(entry.get("value") if isinstance(entry, dict) else entry, ensure_ascii=False)
        for entry in (fields or {}).values()
    )


def _usage_totals(llm_outputs: Dict[str, Any] | None) -> Dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0}
    for section in (llm_outputs or {}).values():
        if not isinstance(section, dict):
            continue
        for out in section.values():
            usage = out.get("usage") if isinstance(out, dict) else None
            for key in totals:
                totals[key] += int((usage or {}).get(key) or 0)
    return totals


def _cost(usage: Dict[str, int], model: str, prices: Dict[str, Any]) -> float | None:
    price = prices.get("models", {}).get(model)
    if not price or not (price.get("input_per_1m") or price.get("output_per_1m")):
        return None
    return round(
        usage["prompt_tokens"] / 1e6 * price["input_per_1m"]
        + usage["completion_tokens"] / 1e6 * price["output_per_1m"],
        5,
    )


def score_case(case: Dict[str, Any], app_md: Any, workflow_text: str = "") -> Dict[str, Any]:
    """Pure scoring: quality = expected values present in the extracted text,
    completeness = expected values captured as structured fields,
    citations = expected references present in analysis/workflow outputs."""
    analysis_text = json.dumps(app_md.llm_outputs or {}, ensure_ascii=False) + workflow_text
    review = (app_md.orchestration or {}).get("review") or {}
    return {
        "quality": _share(case.get("expected_values", []), app_md.document_markdown or ""),
        "completeness": _share(
            case.get("expected_values", []), _field_values(app_md.extracted_fields)
        ),
        "citations": _share(case.get("expected_citations", []), analysis_text),
        "review_status": review.get("status"),
        "review_reasons": [r.get("code") for r in review.get("reasons", [])],
    }


@contextmanager
def _env(overrides: Dict[str, str]) -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in overrides}
    os.environ.update(overrides)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _parse_variant(spec: str) -> tuple[str, Dict[str, str]]:
    name, _, raw = spec.partition(":")
    overrides = dict(pair.split("=", 1) for pair in raw.split(",") if "=" in pair)
    return name, overrides


def run_case(case: Dict[str, Any], workflow: str | None, prices: Dict[str, Any]) -> Dict[str, Any]:
    from app.config import load_settings
    from app.processing import run_content_understanding_for_files, run_underwriting_prompts
    from app.storage import ApplicationMetadata, StoredFile

    settings = load_settings()
    app_md = ApplicationMetadata(
        id=f"eval-{case['id']}-{uuid.uuid4().hex[:6]}",
        created_at=datetime.now(UTC).isoformat(),
        external_reference=case["id"],
        status="pending",
        persona=case["persona"],
        files=[StoredFile(filename=Path(f).name, path=str(ROOT / f)) for f in case["files"]],
    )
    timings: Dict[str, float | None] = {"workflow_s": None}
    started = time.perf_counter()
    app_md = run_content_understanding_for_files(settings, app_md)
    timings["extraction_s"] = round(time.perf_counter() - started, 2)

    started = time.perf_counter()
    app_md = run_underwriting_prompts(settings, app_md)
    timings["analysis_s"] = round(time.perf_counter() - started, 2)

    workflow_text = ""
    if workflow:
        from app.agents import workflows

        factory = getattr(workflows, f"create_{workflow}_workflow")
        started = time.perf_counter()
        result = asyncio.run(factory(settings, app_md.id, persona=case["persona"]))
        timings["workflow_s"] = round(time.perf_counter() - started, 2)
        workflow_text = "\n".join(step["text"] for step in result.get("steps", []))

    usage = _usage_totals(app_md.llm_outputs)
    return {
        "case": case["id"],
        **score_case(case, app_md, workflow_text),
        **timings,
        "tokens": usage["prompt_tokens"] + usage["completion_tokens"],
        **usage,
        "cost": _cost(usage, settings.openai.model_name, prices),
        "model": settings.openai.model_name,
        "agents_api": settings.foundry.agents_openai_api,
    }


def _mean(rows: List[Dict[str, Any]], key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return round(sum(values) / len(values), 3) if values else None


def summarize(results: Dict[str, List[Dict[str, Any]]]) -> str:
    names = list(results)
    means = {n: {m: _mean(results[n], m) for m in METRICS} for n in names}
    base = means[names[0]]
    lines = [
        "| variant | " + " | ".join(METRICS) + " |",
        "|---" * (len(METRICS) + 1) + "|",
    ]
    for name in names:
        cells = []
        for metric in METRICS:
            value, ref = means[name][metric], base[metric]
            delta = (
                f" ({value - ref:+.3g})"
                if name != names[0] and value is not None and ref is not None
                else ""
            )
            cells.append(f"{value:g}{delta}" if value is not None else "n/a")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "Adopt a variant only if quality, completeness and citations are >= baseline "
        "and latency/tokens/cost stay within the agreed tolerance."
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES)
    parser.add_argument("--variant", action="append", default=[], help="name[:ENV=V,...]")
    parser.add_argument("--workflow", choices=["express", "complet", "fraud"], default=None)
    parser.add_argument("--case", action="append", default=[], help="restrict to case id(s)")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    prices = json.loads(args.prices.read_text(encoding="utf-8"))
    cases = [c for c in manifest["cases"] if not args.case or c["id"] in args.case]
    variants = [_parse_variant(v) for v in (args.variant or ["baseline"])]

    out_dir = ROOT / ".tmp" / "eval" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    storage_root = tempfile.mkdtemp(prefix="workbenchiq-eval-", dir=ROOT / ".tmp")

    results: Dict[str, List[Dict[str, Any]]] = {}
    for name, overrides in variants:
        with _env({"UW_APP_STORAGE_ROOT": storage_root, **overrides}):
            rows = []
            for case in cases:
                print(f"[{name}] {case['id']} ...", flush=True)
                try:
                    rows.append(run_case(case, args.workflow, prices))
                except Exception as exc:  # noqa: BLE001
                    rows.append({"case": case["id"], "error": f"{type(exc).__name__}: {exc}"})
            results[name] = rows

    (out_dir / "results.json").write_text(
        json.dumps({"variants": dict(variants), "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = summarize(results)
    (out_dir / "summary.md").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"\nReports: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
