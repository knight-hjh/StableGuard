# Quick start

Use Python 3.10+ on Linux/POSIX and run commands from the repository root.
The ten Dataset project source trees are already in `dataset/projects/`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure your authorized provider URL, API key and exact model ID using the
`SILICONFLOW_*` variables in `.env`. Those names are legacy identifiers, not a
requirement to use SiliconFlow. Keep secrets local.

Restore the selected project's compiler and pinned dependencies from its existing
configuration and lockfiles. Installed node_modules and compiler binaries are not
packaged. No automatic dependency upgrades are intended.

Scanning invokes a paid API and transmits source and rules. Choose one project first:

```bash
JOBS=1 SCAN_OUT=logs/deuro-run python scripts/scan_c1c5.py DEURO
```

To scan the ten analysis projects, use the included project-name list:

```bash
JOBS=1 PROJECT_LIST=dataset/project-list.txt SCAN_OUT=logs/dataset-run \
  python scripts/scan_c1c5.py
```

Use a new output directory for a new run. Existing result files, including failed
ones, are skipped by the historical scanner. The default output limit is still
900 tokens per request, and no global token budget is enforced by this scanner.

Only after results are frozen, evaluate locally:

```bash
python scripts/evaluate_reachable65.py --scan-dir logs/dataset-run \
  --labels dataset/instances.json --output logs/dataset-recognition.json
```

The labels and version-alignment files are not prompt inputs. Historical snapshot
variants are reference material, not automatically merged into the scan. Commands
above have not been executed as part of packaging. See [Dataset limitations](../dataset/README.md)
and [output interpretation](OUTPUT_FORMAT.md).
