# Export provenance

Initial legacy export: 2026-10-18. Dataset source packaging: 2026-10-22.

The original detector, prompt and knowledge-base files are unchanged. Historical
identities are preserved in `provenance/HISTORICAL_METHOD_PINS.json`.
The exported scanner and legacy evaluator now use `dataset/projects/`; supporting
source lookup utilities use the same path. The scanner's default project list is
`dataset/project-list.txt`, and the offline wrapper reads `dataset/instances.json`.
These path-only changes mean those scripts no longer have their original file hashes.
See `provenance/PACKAGING_CHANGES.json` for before/after identities.

`provenance/EXPORT_MANIFEST.json` retains original copied-file identities together
with current exported hashes for modified paths. `provenance/SHA256SUMS` covers the
listed code and metadata, not every documentation/configuration file. Dataset source
hashes are separately listed in `dataset/source-files.json` and `dataset/SHA256SUMS`.
Hashes were generated from bytes used in the copy/write operation; no post-copy
validation or test execution was performed.

The 65 historical records retain their original fields. Source bindings were added
without replacing labels. The prior normalized metadata bytes remain available as
`provenance/REACHABLE65_ORIGINAL_LABELS.json`. The original audit-derived CSV is
unchanged. The package does not convert historical mechanism matches into newly
validated vulnerabilities.

Project copies include available source, tests, configuration, locks and vendored
libraries. Original workspace sources were not modified. Declared checkout HEADs
and prior snapshot manifests are provenance observations, not freshly authenticated
commit-tree membership. Existing uncertainty is retained in the source mappings.

No inference API calls, compilation, package installation, tests, dependency downloads,
Git commands or GitHub upload were performed. The generic API client is not claimed
to be the complete frozen executor of every historical experiment.
