# Aurora 1.5 model and data contract

## Model role

Aurora is a foundation model for weather and Earth-system forecasting, not a conversational model.
Aurora 1.5 extends the open model family with additional Earth-system variables and deterministic
and ensemble checkpoints. Confirm exact checkpoint capabilities and licensing against the current
Microsoft Research release before deployment.

## PrevaIQ managed input contract

The deployed Aurora-v1p5 serving package used by PrevaIQ expects a NetCDF initial-condition payload:

- exactly two historical time steps;
- 19 required surface inputs;
- atmospheric `z`, `u`, `v`, `t`, and `q`;
- latitude, longitude, and time coordinates compatible with the endpoint;
- no missing required variables.

The canonical required-variable sets live in `app/aurora.py`. Do not duplicate them in another
runtime module.

The endpoint returns one or more NetCDF prediction files. PrevaIQ extracts:

- valid time;
- 2 m temperature;
- 10 m wind speed;
- 10 m wind gust where supplied;
- hourly precipitation and snowfall;
- cloud cover;
- forecast maxima/totals and a bounded hazard window.

Unit conversion belongs in the backend normalizer. The frontend displays normalized values and
must not infer units from arbitrary NetCDF names.

## Initial-condition sources

ERA5 and other compatible analysis products can supply initial conditions, but data acquisition is
a separate governed pipeline. Validate:

- source license and access terms;
- observation/analysis time freshness;
- variable names and units;
- coordinate ordering and longitude convention;
- pressure levels;
- temporal cadence;
- spatial grid compatibility;
- missing values.

Never commit production weather datasets, CDS credentials, account keys, or signed Blob URLs.

## Real-time versus batch

- **Interactive managed endpoint**: single dossier, deterministic model, short horizon, customer
  conversation and triage.
- **Batch/portfolio**: many insured locations, controlled scheduling, ensemble or multiple
  scenarios, aggregate exposure reporting.

Do not run a real-time endpoint continuously solely for occasional batch work. Do not make the
interactive case UI wait for an unbounded portfolio job.

## Open weights and fine-tuning

Use open weights when the requirement is local research, a custom variable, a custom domain, or a
serving contract not supplied by the managed model. This is separate from PrevaIQ product
configuration and may require substantial GPU capacity, checkpoint storage, weather expertise,
and evaluation data.

Before fine-tuning:

1. define the target variable and decision use;
2. establish a baseline and holdout periods;
3. confirm data coverage, units, and leakage controls;
4. budget training and serving compute;
5. define checkpoint selection and rollback;
6. obtain approval before provisioning billable GPU resources.

Useful primary sources:

- Microsoft Research Aurora 1.5 announcement:
  <https://www.microsoft.com/en-us/research/blog/aurora-1-5-extending-open-foundation-models-for-weather-and-earth-system-applications/>
- Official open-source implementation: <https://github.com/microsoft/aurora>
- Official model collection: <https://huggingface.co/microsoft/aurora>
