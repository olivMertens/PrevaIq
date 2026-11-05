# Seeded demo files

Fictitious documents and photos referenced by the PrevaIQ demo cases: the cases seeded by
`scripts/seed_customer360.py` (from `scripts/seed_data`) and a demo case uploaded in production.
Everything is invented — people, companies, SIRET/RPPS numbers, contracts, amounts — and every
PDF carries the footer "Document fictif — démonstration PrevaIQ". No real insurer, company name
or logo is used; photos show no faces, logos or readable plates.

- `manifest.json` lists every referenced file (`app_id`, `filename`, repo-relative `path`).
  `origin: generated` files live in `<app_id>/<filename>`; `origin: repo` entries point to an
  existing asset (mortgage cases, dental thread) instead of duplicating it. Generated photos keep
  their MAI-Image-2.6 prompt and generation date in `generated_with` (per photo for the zip).
- PDFs are rebuilt byte-for-byte from the seed data; photos are generated once and then kept.

## Regenerate

```powershell
.\.venv\Scripts\python.exe scripts\generate_seeded_demo_files.py           # PDFs + manifest
.\.venv\Scripts\python.exe scripts\generate_seeded_demo_files.py --photos  # + missing photos
.\.venv\Scripts\python.exe scripts\generate_seeded_demo_files.py --photos --force --only app-hab-005
```

Photos need an MAI-Image-2.6 deployment (`--endpoint` / `--deployment`, or `MAI_IMAGE_ENDPOINT` /
`MAI_IMAGE_DEPLOYMENT`) and Entra ID credentials (`az login`); requests are throttled to 3 per
minute. Check the result with `pytest tests/test_seeded_demo_assets.py`.

## Restore an environment

`seed_customer360.py` stores these files with the cases it seeds. For an environment whose cases
exist but whose files are missing (the API key is read from the environment, never printed):

```powershell
$env:PREVAIQ_API_KEY = "<key>"
.\.venv\Scripts\python.exe scripts\audit_demo_files.py --api-url https://<api-host>
.\.venv\Scripts\python.exe scripts\restore_demo_files.py --api-url https://<api-host> --dry-run
.\.venv\Scripts\python.exe scripts\restore_demo_files.py --api-url https://<api-host>
```

The restore is idempotent: files the API already serves are skipped, the others are uploaded with
`PUT /api/applications/{app_id}/files/{filename}`.
