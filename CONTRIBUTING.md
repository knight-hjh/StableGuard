# Contributing

This repository preserves a historical implementation. Changes should make their
scope explicit rather than silently redefining its behavior.

## Change boundaries

- Documentation and packaging changes must not claim new detection capabilities.
- Detector, prompt, rule, context-selection, or matching changes define a changed method/configuration.
- Keep original results and source-version records when proposing corrections.
- Do not convert uncertain or technically failed results into confirmed positives or negatives.
- Do not commit credentials, private code, raw provider headers, or unreviewed model artifacts.

## Reporting an issue

State the entry point, sanitized command, environment, project revision, and the
stage where execution differs from expectations. Distinguish build problems,
transport problems, invalid output, and disagreement over a defect mechanism.

For a suspected false positive, identify the claimed mechanism and source evidence
that blocks it. For a suspected miss, identify the expected mechanism and whether
the relevant code entered the analyzed input. Do not rely solely on a model's
explanation as proof of either outcome.

## Proposing a change

Explain whether it affects code selection, model input, transport, parsing,
matching, or documentation. Record validation actually performed; if none was
performed, say so. Do not add automatic inference jobs to pull requests or CI.

No test suite or passing CI run is claimed for this export. Any future validation
should avoid external inference by default, isolate project build tools, and use
separately authorized credentials and budgets when external calls are necessary.

The repository owner must determine the license and contribution terms before
accepting a public contribution policy as legally binding.
