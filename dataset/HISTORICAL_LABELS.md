# Reachable-65 evaluation metadata

`instances.json` is a field-preserving serialization of the historical
Reachable-65 selection. It contains 65 positive labels and historical file aliases:

| Category | Labels |
| --- | ---: |
| C1 | 15 |
| C2 | 14 |
| C3 | 10 |
| C4 | 14 |
| C5 | 12 |
| Total | 65 |

This file is evaluation-only. Do not concatenate it into detection prompts. The
scanner does not load it. Historical detection flags are provenance, not new
measurements produced by this export.

Project sources are now packaged under `projects/`. Packaging does not establish a fresh
source-version validation. It is not the later 62-root dataset. See
`../docs/EVALUATION.md` for matching limitations and reproduction prerequisites.
