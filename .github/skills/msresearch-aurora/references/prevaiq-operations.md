# PrevaIQ Aurora operations

## Configuration precedence

Persisted admin configuration takes precedence over deployment environment variables. If no admin
configuration exists, the adapter reads:

- `AURORA_ENABLED`
- `AURORA_FOUNDRY_ENDPOINT`
- `AURORA_DEPLOYMENT_NAME`
- `AURORA_ENSEMBLE_DEPLOYMENT_NAME`
- `AURORA_INITIAL_CONDITION_BLOB_URL`
- `AURORA_CHANNEL_CONTAINER_URL`
- `AURORA_BLOB_CHANNEL_SAS_URL` for legacy rollback only
- `AURORA_ENDPOINT_TOKEN` only when Azure AD is explicitly disabled
- `AURORA_TOKEN_SCOPE`
- `AURORA_TIMEOUT_SECONDS`
- `AURORA_POLL_INTERVAL_SECONDS`
- `AURORA_USE_AZURE_AD`
- `AURORA_DEFAULT_HORIZON_HOURS`

The admin surface must never accept or return tokens, keys, or SAS query strings.

Some Azure ML managed endpoints are provisioned with **Key** authentication rather than
Microsoft Entra authentication. For those endpoints set `AURORA_USE_AZURE_AD=false` and
provide `AURORA_ENDPOINT_TOKEN` through a secret reference. The adapter sends the key as
`Authorization: Bearer <key>`; it is never persisted in the Aurora admin configuration.

## Endpoint protocol

The model is not a latitude/longitude JSON API. PrevaIQ:

1. downloads and validates the configured initial-condition NetCDF;
2. obtains a managed-identity token for the ML scope or loads the deployment-injected endpoint key;
3. creates a short-lived user-delegation SAS for the configured task container;
4. uploads the input under a unique task prefix;
5. posts a `task_submission` message to the endpoint;
6. polls with `task_info` until success, failure, or the configured timeout;
7. downloads the result NetCDF files from the task prefix;
8. extracts the nearest grid point and computes bounded insurance signals;
9. persists the result in the dossier with provenance.

Every loop is bounded. A service failure is an error, never a synthetic forecast.

## Azure identity

Grant only the roles needed by the Container App managed identity:

- endpoint invocation permission on the managed online endpoint;
- `Storage Blob Data Reader` for the initial-condition Blob;
- Blob data permissions sufficient to create delegated SAS and read/write/create task artifacts on
  the task container.

Keep the initial-condition and task containers private. Prefer resource-scoped assignments over
subscription-wide roles.

## Focused validation

From the repository root:

```powershell
uv run pytest tests/test_aurora.py
uv run ruff check app/aurora.py app/aurora_config.py app/aurora_admin_api.py tests/test_aurora.py
uv run ruff format --check app/aurora.py app/aurora_config.py app/aurora_admin_api.py tests/test_aurora.py
```

From `frontend/`:

```powershell
npm run type-check
npx eslint src/components/admin/AuroraAdminTab.tsx src/components/case/AuroraRiskPanel.tsx src/components/case/AuroraForecastChart.tsx
npm run test:i18n
npm run build
```

Infrastructure changes must keep Bicep and Terraform equivalent and validate both:

```powershell
az bicep build --file infra/main.bicep
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
```

Use `scripts/test_aurora_endpoint.py` only after a real endpoint and private input/channel resources
exist. It can incur inference cost.

## Demo verification

1. Sign in as an administrator and open the Aurora admin tab.
2. Confirm no secrets are requested or rendered.
3. Save a disabled configuration and reload it.
4. With real resources, enable Aurora and run the live readiness test.
5. Open an automotive or property claim with a geocoded loss location.
6. Run the configured short-horizon deterministic forecast.
7. Verify the hourly timeline, hazard window, actions, customer guidance, and provenance.
8. Verify a non-admin receives HTTP 403 from the dedicated admin routes.
9. Confirm no demo dialog asset or file reference was changed by the feature.
