---
name: msresearch-aurora
description: "Assess, configure, test, deploy, troubleshoot, or extend Microsoft Research Aurora 1.5 weather and Earth-system capabilities in PrevaIQ. Use when requests mention Aurora, Aurora-v1p5, Foundry managed endpoints, weather-risk evidence, ERA5 or NetCDF initial conditions, task/Blob inference, deterministic versus ensemble forecasts, real-time versus batch weather workflows, or Aurora fine-tuning. Prefer PrevaIQ's managed endpoint adapter for product integration; use open-weight workflows only for explicit research or fine-tuning work."
license: MIT
---

# Microsoft Research Aurora 1.5 in PrevaIQ

## Objective

Operate Aurora as a bounded, advisory weather-evidence source for insurance workflows. Preserve
human accountability: Aurora may prioritize review, suggest customer-call actions, and align event
timing with weather evidence, but it must never approve, deny, price, or pay a claim.

This project uses a Foundry/Azure Machine Learning managed endpoint with a task/Blob protocol.
Do not replace it with an OpenAI-style chat call or with the upstream Norway prototype.

## Choose the path

1. **Configure or test PrevaIQ**: follow the managed endpoint workflow below and load
   [PrevaIQ operations](./references/prevaiq-operations.md).
2. **Assess model suitability or explain Aurora**: load
   [model and data contract](./references/model-and-data.md).
3. **Prepare input data or evaluate output quality**: load
   [evaluation workflow](./references/evaluation.md).
4. **Fine-tune or run open weights**: first explain that this is a separate GPU research workflow.
   Do not modify the product adapter until the resulting checkpoint and serving contract are known.
   Consult the official `microsoft/aurora` repository and the attributed upstream vibe-kit skill.

## Managed endpoint workflow

1. Confirm the Azure tenant, subscription, region, model asset, quota, endpoint type, and estimated
   cost. Never create billable GPU compute without explicit user approval.
2. Use real-time managed inference for the interactive single-case demo. Reserve batch processing
   for later portfolio exposure sweeps.
3. Configure the admin UI with non-secret values only:
   - managed endpoint URL;
   - deterministic and ensemble deployment identifiers;
   - private initial-condition NetCDF Blob URL;
   - private task-channel container URL;
   - default interactive forecast horizon.
4. Keep authentication on managed identity. Never persist bearer tokens, account keys, SAS URLs,
   or URL query strings. The backend creates short-lived delegated Blob SAS access at runtime.
5. Run the admin readiness test. It must verify:
   - feature enabled;
   - managed identity token acquisition;
   - endpoint reachability;
   - NetCDF download and structural validation;
   - delegated Blob-channel access.
6. Submit a bounded dossier forecast, poll to the configured timeout, parse all returned NetCDF
   outputs, persist the normalized result and provenance, and show the hourly evidence timeline.
7. Verify the UI keeps expert review explicit and does not turn model output into a decision.

## Product invariants

- Treat the managed endpoint's task/Blob schema as the source protocol.
- Require two input history steps, all required variables, and a valid time axis.
- Default the interactive demo to a short 6-12 hour horizon; allow a longer horizon only when the
  deployed model and input grid have been evaluated for it.
- Keep retry and polling loops bounded by timeout and interval settings.
- Persist normalized metrics, hazard window, model, input source, request time, and location.
- Expose explicit disabled, unconfigured, running, failed, and complete states.
- Surface service errors; do not generate plausible-looking weather as a fallback.
- Use deterministic inference for interactive triage. Use ensemble inference only when the
  uncertainty experience and compute budget are explicitly designed.

## Insurance value pattern

Translate forecast output only into:

- weather-aware case triage;
- predicted hazard-window context;
- proactive customer contact and safety guidance;
- preservation of timestamped evidence;
- prioritization of adjuster or expert review;
- comparison of reported timing with traceable model evidence.

Measure triage time, avoidable information requests, handler preparation time, and escalation
accuracy against the current workflow. Never present projected savings as achieved ROI.

## Canonical implementation surfaces

- `app/aurora.py`: task/Blob client, input validation, normalized output, bounded decision support.
- `app/aurora_config.py`: audited non-secret configuration persistence.
- `app/aurora_admin_api.py`: admin snapshot and live readiness tests.
- `api_server.py`: public dossier forecast and internal admin routes.
- `frontend/src/components/admin/AuroraAdminTab.tsx`: secure readiness and setup experience.
- `frontend/src/components/case/AuroraRiskPanel.tsx`: dossier evidence and expert-review UI.
- `infra/main.bicep` and `infra/terraform/`: paired settings, identity, and Blob permissions.
- `tests/test_aurora.py` and `scripts/test_aurora_endpoint.py`: contract and endpoint checks.

## Validation

After changes, run the smallest applicable checks from
[PrevaIQ operations](./references/prevaiq-operations.md). For model or input changes, also run the
evaluation harness before generalizing the change. Verify English, French, and German translation
parity for all user-facing UI.

## Provenance

This project skill is an adapted, lightweight workflow derived from the Microsoft Research
Vibe Kit `msresearch-aurora` skill. Heavy example applications, research PDFs, checkpoints, and
NetCDF/GRIB fixtures are intentionally not vendored. See [NOTICE](./NOTICE.md) and
[LICENSE](./LICENSE).
