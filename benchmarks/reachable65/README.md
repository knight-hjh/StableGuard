# Reachable-65 evaluation metadata

`evaluation_only.json` is a field-preserving serialization of the historical
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

The file does not contain complete project sources or establish a fresh
source-version validation. It is not the later 62-root benchmark. See
`../../docs/EVALUATION.md` for matching limitations and reproduction prerequisites.
