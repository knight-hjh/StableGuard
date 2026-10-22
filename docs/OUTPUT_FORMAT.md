# Output interpretation

The following examples describe fields, not experimental measurements.

## Per-project file

The scanner normally creates `SCAN_OUT/<sanitized-project-name>.json`. Depending
on where execution stops, some fields may be absent.

| Field | Interpretation |
| --- | --- |
| `project` | Local project directory name |
| `status` | Project-level execution outcome |
| `n_candidates` | Candidates produced by the selected static detectors |
| `model` | Configured model identifier, when recorded |
| `ablation_mode` | Selected historical prompt configuration |
| `all_verdicts` | Per-candidate decisions and recorded candidate errors |
| `findings` | Positive judgments with model reasoning |
| `usage` | Aggregated recorded usage for returned calls |
| `error` | Project-level failure description, when present |

Candidate records can contain `sub`, `contract`, `file`, `function`, `line`,
the static detector's reason, and model output fields. These are reported
locations and classifications, not independently checked defect identities.

## Project status versus candidate status

| Project status | Meaning |
| --- | --- |
| `ok` | Candidate iteration finished; individual candidates may still have errors |
| `ok_no_candidates` | No candidates were produced for the parsed input |
| `timeout` | The project parsing/detection alarm interrupted processing |
| `error` | A project-level exception was recorded |
| `crash` | The worker recorded an exception outside normal project handling |

`skip` is a worker progress message when the output already exists; it does not
establish that the existing result is valid or complete. Missing fields must not
be replaced with invented success values.

## Candidate judgments

| `defect_present` | Meaning in this implementation |
| --- | --- |
| `true` | Positive historical type/mechanism recognition |
| `false` | The model rejected that type/mechanism classification |
| `"uncertain"` | The model/parser retained an uncertain outcome |
| `"error"` | A candidate-level exception was recorded |
| Missing or null | No usable Boolean judgment was recorded; inspect the raw circumstances |

The legacy parser can normalize string-valued Boolean answers. It is not a
full evidence validator, and the generic scanner does not enforce all strict
response gates used by later experiment-specific executors.

`findings` contains positive model judgments, not source-reviewed true positives.
The absence of a finding does not distinguish a semantic rejection from a
technical failure without consulting the candidate records.

## Costs

The usage object contains prompt, completion, and total token counts, call count,
model identifier, and accumulated LLM call elapsed time. These values do not
include a complete end-to-end timer for project parsing, compilation, queueing,
or review. Failed attempts may not have complete provider usage records.

Do not report `usage.elapsed_seconds` as total tool runtime. Do not compare a
per-call average with a per-project or per-source average without defining the
denominator and comparable workloads.

## Offline evaluation output

The Reachable-65 wrapper labels its report `LEGACY_RECOGNITION_ONLY`. It provides
label-to-alert matches, per-category recognition recall, unmatched alerts, project
coverage information, and recorded errors/uncertainty.

Its `strict_precision` and `strict_f1` fields are intentionally null. Computing
source-validity metrics requires separate review and an explicit decision on
alert-level versus defect-root-level counting. Unresolved items remain unresolved.
