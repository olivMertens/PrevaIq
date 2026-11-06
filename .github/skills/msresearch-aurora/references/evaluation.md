# Aurora evaluation workflow

## Evaluate the weather model separately from insurance value

Two independent questions must pass:

1. Is the forecast technically valid and useful for the selected location, variable, and horizon?
2. Does presenting this evidence improve the human insurance workflow without increasing unsafe
   automation or false confidence?

## Weather checks

- NetCDF opens and contains the complete required contract.
- Coordinates, units, valid times, and lead times are correct.
- Values are finite and physically plausible.
- Autoregressive output does not diverge over the selected horizon.
- Forecast metrics are compared with an accepted reference or observations over representative
  events, not one favorable case.
- Deterministic and ensemble results are not presented as interchangeable.
- Known model, input, and spatial-resolution limitations are visible.

Track error by variable, lead time, geography, season, and hazard severity. Preserve the model
identifier, input timestamp/source, endpoint version, and evaluation dataset version.

## Insurance workflow checks

Use representative but fictitious dossiers and compare against the existing handler workflow:

- time to identify a weather-related priority case;
- time to prepare a customer call;
- avoidable requests for already available evidence;
- appropriate expert escalations;
- incorrect or unnecessary escalations;
- agreement between reported event timing and weather evidence;
- handler understanding of provenance and limitations.

Keep Aurora advisory. Include cases where the model is unavailable, the signal is low, evidence
conflicts, or the forecast is outside the evaluated geography/horizon.

## Change gate

Run `scripts/eval_pipeline.py` before generalizing a model, endpoint, extraction, threshold, or
prompt change. Do not tune severity thresholds on the same events used for the final demonstration.
Document the baseline, candidate, acceptance criteria, regressions, latency, token/compute cost, and
human-review outcome.

## Demo claims

Demonstrate workflow levers, not unverified savings. Say that the feature can reduce triage or
preparation effort only when supported by measured comparisons. Never describe forecast accuracy
or financial ROI as achieved based solely on a successful endpoint call.
