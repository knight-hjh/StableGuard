# Changelog

## 2026-10-22

- Consolidated Dataset labels and project sources under dataset/.
- Added 10 analysis trees and 22 historical reference trees, with byte hashes and source-version mapping.
- Updated exported script path defaults without changing detector or matching semantics.
- Preserved original label metadata and original method hashes in provenance/.
- Documented source-version and redistribution prerequisites; no runtime validation performed.

## Unreleased

### 2026-10-18: Legacy repository preparation

- Isolated the legacy C1-C5 scanner and its required local modules.
- Preserved the historical detector, context augmentation, prompt, rules, and matcher.
- Added explicit Reachable-65 evaluation metadata and an offline matching wrapper.
- Recorded source origins, historical core hashes, and checksum scope.
- Added environment placeholders, editable-install metadata, Git ignore rules, and issue templates.
- Added usage, output, evaluation, reproducibility, contribution, and security documentation.

No detector accuracy improvement, successful reproduction, passing installation,
test execution, or inference run is claimed by this packaging change. License,
author/citation details, redistribution review, and runtime validation remain
publication prerequisites.
