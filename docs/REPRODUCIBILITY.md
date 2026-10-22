# Reproducibility guide

## Define the experiment before running it

Record whether the task is fresh project discovery, a same-candidate rerun,
historical recognition evaluation, or source-validity review. These tasks do not
share identical inputs or outcome definitions.

The generic scanner accepts projects and discovers candidates. The rerun script
accepts existing candidate locations and extracts source excerpts. Neither should
be described as the other configuration merely because both use the same model.

## Preserve input identities

- Record the repository URL and exact revision of every project.
- Preserve dependency locks, compiler identity, remappings, and build settings.
- Record relevant local changes rather than assuming a project name identifies its source.
- Keep the selected dataset metadata separate from model inputs.
- Identify the StableGuard code and rule versions, including deliberate changes.

`provenance/HISTORICAL_METHOD_PINS.json` identifies five historical core files.
`provenance/EXPORT_MANIFEST.json` inventories the exported copies. These records
do not pin Python packages, hosted model weights, project sources, or every
historical executor. The requirements specify ranges, not a frozen environment.

## Record the inference configuration

Record the provider, endpoint, requested model ID, returned model ID if available,
temperature, output limit, thinking-related fields, concurrency, and retry policy.
Do not include API keys or authorization headers in an experiment record.

The generic scan uses 900 output tokens per candidate and the copied client's
retry behavior. If a model needs a different transport or output limit, record a
separate configuration instead of attributing that result to an unchanged run.

The scanner's result files do not preserve every raw response or configuration
field needed for exact replay. Retain authorized artifacts separately when a
formal experiment requires them; this document does not imply that the generic
scanner already creates a complete request-level ledger.

## Separate outcomes and review

Report compilation and coverage gaps, transport/response failures, semantic
judgments, and independent source-review conclusions separately. Retain partial
outputs and do not silently rerun failures under a different model.

Historical dataset matching uses project/subtype/file aliases. Strict review
requires source version, relevant guards, financial role, reachable behavior,
and the claimed mechanism. Do not treat a file-level match as a one-to-one
confirmed defect root.

## Record resources using a declared denominator

Keep provider-reported input/output tokens distinct from estimates. Specify
whether retries and optional review are included. For elapsed time, distinguish
LLM-call duration from end-to-end wall time and declare whether averaging is by
request, project, source file, or dataset instance.

Use `examples/experiment-record.example.json` as a manual recording template.
It is not an executable manifest and does not authorize API calls. Its null values
must be filled from actual measurements, not inferred from old tables.

## What remains before a validated release

Installation, local compilation, execution, and any inference smoke test require
separate validation. The package has no claimed passing CI or end-to-end result.
Exact historical numerical reproduction additionally requires the original
source snapshots and the corresponding experiment/review records.
