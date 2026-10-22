# Evaluation scope and terminology

## Two different metadata sources

`stablecoin_specific_full.csv` is the original finding pool consumed by the
historical evaluator. It is not an explicit selection of the 65 reachable labels.
Its interpretation also depends on local project availability and optional
inheritance-resolution records, which are not bundled.

`benchmarks/reachable65/evaluation_only.json` preserves the explicit historical
65-label selection and its already-expanded file aliases. Its class distribution
is C1=15, C2=14, C3=10, C4=14, C5=12. Historical model-hit fields are retained as
provenance, not recomputed results or inputs to the scanner.

## Offline wrapper

`scripts/evaluate_reachable65.py` is a new packaging wrapper around the unchanged
legacy `match` function. It reads saved per-project outputs and reports:

- Number of matched labels out of the fixed 65-label denominator.
- Per-category recognition recall.
- Positive-alert counts and their historical benchmark matches.
- Missing projects, recorded candidate errors, and uncertain results.
- Unmatched alerts requiring independent source review.

The matcher uses project, subtype, and allowed file basenames. It does not enforce
exact function, commit, defect-root identity, or one-to-one alert/label matching.
Where file information is absent, the original matcher permits a project/subtype
fallback. These limitations are preserved for historical comparison.

The output is consequently called **legacy recognition recall**, not certified
current-version vulnerability recall. Missing or failed analysis is disclosed;
the wrapper does not label technical failures as true negatives.

## Precision and additional findings

An unmatched alert is not automatically false. A benchmark match is also not
independent proof that the supplied revision still contains the claimed defect.
Compute source-validity precision only after reviewing the exact version,
mechanism, guards, and relevant execution paths. Preserve unresolved judgments
and report their coverage.

Do not combine alert-level acceptance counts with benchmark-label recall into
an F1 without first aligning the evaluation units. The wrapper intentionally
leaves precision and F1 unset.

## Reproduction requirements

This code export alone cannot reproduce the historical numerical results.
Reproduction also requires the exact project revisions, dependencies, compiler
settings, input selection, prompt/transport configuration, and any reviewed
outputs. Models and hosted aliases may change independently of this repository.

The later 62-root benchmark, newer M0-M3 pipeline, and unrelated real-world scans
are outside this export. The retained historical labels have known source-version
and matching limitations; they should not be relabeled as newly source-validated
ground truth merely because they are included here.
