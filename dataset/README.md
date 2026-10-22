# StableGuard Dataset

This directory contains the legacy 65-instance Dataset, its source mapping, and
actual Solidity project source trees. It is not the later 62-root collection.

## Files

- `instances.json`: the original 65 records, with additive source bindings.
- `projects/PROJECT/`: source copies of the ten analysis working trees.
- `projects/snapshots/SNAPSHOT/`: 22 available historical reference trees.
- `projects.json`: origins, declared/recorded commits, licenses and export counts.
- `source-files.json` and `SHA256SUMS`: paths and byte hashes captured during copying.
- `version-alignment.json`: preserved pre-existing version-alignment observations.
- `excluded-files.json`: omitted paths and reasons, including un-followed symlinks.
- `project-list.txt`: analysis project names for the scanner.

There are 65 records across 10 projects: C1=15, C2=14, C3=10, C4=14, C5=12.
The source bundle contains 21337 files (10090 Solidity),
324488284 bytes, across 32 versioned or analysis trees.
Shared dependencies and multiple versions contribute separate files to these totals.

## Locate source for an instance

Find the `evaluation_id` in `instances.json`. Its `source_binding` contains:

- `analysis_project_path`: the complete packaged source-tree location, relative to repository root.
- `analysis_source_candidates`: existing target-file candidates and their hashes.
- `analysis_location_status`: whether an exact path or a basename matched.
- `audit_commits` and `audit_reference_status`: historical audit-version evidence.
- `historical_reference_snapshots` and `audit_target_sources`: available reference source.
- `remaining_version_gaps`: unresolved differences recorded before this packaging task.

64/65 records have a matching target
filename/path in the analysis copies. Records without such a candidate:
GT-037.
Filename matching does not establish function identity, vulnerable-version identity
or defect validity. All 65 retain `vulnerable_source_certified=false`: this packaging
operation has not performed a fresh audit of every vulnerability binding.

An analysis copy preserves available local working-tree bytes. Its declared Git
HEAD is provenance, not proof that its files are pristine at that commit. Historical
snapshot names and recorded commit fields likewise do not constitute new Git-tree
authentication. Some registry links were already disputed; they remain references,
not silently accepted vulnerable versions. The original historical 65-label JSON
is retained at `../provenance/REACHABLE65_ORIGINAL_LABELS.json`.

## Included and excluded content

The export includes first-party source, interfaces, tests, scripts, build configuration,
lockfiles, text documentation and available vendored dependency source. Source bytes
are copied without rewriting Solidity, pragma directives, dependency versions or guards.
Installed `node_modules`, Git internals, environment/credential files, audit PDFs,
build output, caches, logs and non-source binary assets are excluded. Symlinks are
not followed. Exclusions mean this is a source-tree export, not a ready-made binary
or fully offline build environment. Review `excluded-files.json` if a dependency
must be restored. No dependency was downloaded in this task.

## Run and evaluate

From the repository root, scan `dataset/projects/PROJECT/` with
`python scripts/scan_c1c5.py PROJECT`. The scanner does not read instance labels.
Use `scripts/evaluate_reachable65.py` only after scan outputs are fixed.
See [evaluation semantics](../docs/EVALUATION.md) before interpreting counts.

## Redistribution

Included projects and vendored libraries keep their upstream licenses and notices.
The absence of a standalone license file does not imply unrestricted permission.
Audit text and internal finding records may need separate publication clearance.
The source inventory is not a license opinion or a certification of all 65 labels.
